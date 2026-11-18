"""The `prompt` mode: a typed `/sdlc` locks the session, `approve plan` and `sdlc off` release it.

`prompt` (UserPromptSubmit): a typed `/sdlc` locks code edits in that session; a reply of
exactly `approve plan` unlocks them and binds the approval to the hash of
each `.sdlc/*/plan.md`; with more than one plan.md the reply names the plan, `approve plan
<folder>`. When that plan holds an `sdlc-scope` block, its patterns are frozen into the approval
and only matching files may be edited. A reply of exactly `sdlc off` releases the session.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from sdlc_hooks.core import UNLOCK_WORDS, emit, gate_home, log_event, now, session_file
from sdlc_hooks.jira.markers import arm_intake, intake_pending, jira_marker_exists, jira_request, mark_jira
from sdlc_hooks.plan.approval import approve, intake_start_note
from sdlc_hooks.snyk_gate import on_snyk_command

SDLC_PROMPT = re.compile(r"/(?:[\w-]+:)?sdlc(?:\s|$)")
APPROVE_PROMPT = re.compile(
    r"approve plan(?:[ \t]+(?P<slug>[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9_-])?))?[\s.!]*",
    re.IGNORECASE)
RELEASE_PROMPT = re.compile(r"/?sdlc off[\s.!]*", re.IGNORECASE)
RELEASE_INTAKE_PROMPT = re.compile(r"/?sdlc intake off[\s.!]*", re.IGNORECASE)
SNYK_PROMPT_START = re.compile(r"sdlc snyk(?=\s|$)", re.IGNORECASE)  # with a slash it is the host's /sdlc command

# A link to a ticket in an owner prompt marks the session (every non-read MCP tool is denied there until `sdlc off`).
# A bare key does not: UTF-8, SHA-256 and ISO-8601 look like keys, and a plain run would lose its MCP writes.
JIRA_CUE = re.compile(r"atlassian\.net/browse/")


def start_run(data: dict, lock: Path, approved: Path, text: str) -> None:
    request = jira_request(text)
    if request is not None or JIRA_CUE.search(text):
        mark_jira(data)  # before the lock: a failed write cannot leave a lock with no marker
    if request is not None:
        arm_intake(data, request)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"since": now(), "cwd": data.get("cwd", "")}))
    approved.unlink(missing_ok=True)
    notes = [
        "sdlc-gate: code edits in this project are locked for this session until the owner "
        f"replies {UNLOCK_WORDS}. Files under .sdlc/ stay writable."
    ]
    if request is not None:
        notes.append(intake_start_note(request))
    rules = gate_home() / "rules" / "sdlc.md"
    if not rules.is_file():
        notes.append(f"sdlc-gate: {rules} is not installed, so the risk table this command uses is "
                     "missing. Tell the owner to run scripts/install.sh from the sdlc repo.")
    emit("UserPromptSubmit", additionalContext=" ".join(notes))


def release(data: dict, lock: Path, approved: Path, text: str) -> None:
    had_marker = jira_marker_exists(data)
    lock.unlink(missing_ok=True)
    approved.unlink(missing_ok=True)
    session_file(data, "jira").unlink(missing_ok=True)
    session_file(data, "jira-intake").unlink(missing_ok=True)
    line = log_event(data, "release", text)
    note = " MCP writes are no longer blocked." if had_marker else ""
    emit("UserPromptSubmit", additionalContext=(
        f"sdlc-gate: released by the owner ({line}); code edits are no longer gated in this session.{note}"))


def release_intake(data: dict, text: str) -> None:
    """The owner accepts a Jira run whose ticket label could not be checked. Only the pending intake goes: the
    write block and the code lock stay, which `sdlc off` would also lift."""
    if intake_pending(data) is None:
        return
    session_file(data, "jira-intake").unlink(missing_ok=True)
    line = log_event(data, "intake-off", text)
    emit("UserPromptSubmit", additionalContext=(
        f"sdlc-gate: the owner released the Jira intake ({line}), so the ticket's label was not checked. `approve plan` "
        "is no longer held for it; MCP writes stay denied and code edits stay locked."))


def on_prompt(data: dict) -> None:
    text = unicodedata.normalize("NFC", str(data.get("prompt", ""))).strip()
    lock, approved = session_file(data, "locked"), session_file(data, "approved")
    if lock is None or approved is None:
        return
    gated = lock.exists() or approved.exists() or jira_marker_exists(data)
    if RELEASE_PROMPT.fullmatch(text):
        if gated:
            release(data, lock, approved, text)
    elif RELEASE_INTAKE_PROMPT.fullmatch(text):
        release_intake(data, text)
    elif SNYK_PROMPT_START.match(text):
        on_snyk_command(data, text)
    elif SDLC_PROMPT.match(text):
        start_run(data, lock, approved, text)
    elif gated:
        approval = APPROVE_PROMPT.fullmatch(text)
        if approval:
            approve(data, lock, approved, text, approval.group("slug"))
        elif JIRA_CUE.search(text):
            mark_jira(data)
