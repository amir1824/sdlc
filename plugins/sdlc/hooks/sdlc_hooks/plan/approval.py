"""`approve plan`: choosing the plan, hashing it and recording what the approval freezes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from sdlc_hooks.core import emit, log_event, now, project_root, session_file
from sdlc_hooks.jira.markers import NO_KEY, intake_pending, jira_label
from sdlc_hooks.plan.frozen_tests import TESTS_BLOCK, TESTS_WRITER, frozen_key, has_block, parse_tests, previous_tests
from sdlc_hooks.plan.scope import SCOPE_BLOCK, parse_scope
from sdlc_hooks.snyk_gate import pin_snyk_base

def plan_sources(root: Path) -> dict[str, bytes]:
    """Each .sdlc/*/plan.md as read once: its path relative to the project, and its bytes."""
    return {str(plan.relative_to(root)): plan.read_bytes() for plan in sorted(root.glob(".sdlc/*/plan.md"))}


def hash_sources(sources: dict[str, bytes]) -> dict[str, str]:
    return {name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()}


def plan_hashes(root: Path) -> dict[str, str]:
    return hash_sources(plan_sources(root))


def choose_plan(sources: dict[str, bytes], slug: str | None) -> tuple[str | None, str]:
    """(the plan to approve, "") or (None, why not). With several plan.md files and no scope block in
    any, the choice decides nothing and no name is needed: (None, ""). Once one holds a block the owner
    names the plan, because the choice decides which paths may be edited."""
    names = sorted(sources)
    if slug:
        target = f".sdlc/{slug}/plan.md"
        return (target, "") if target in sources else (None, f"no plan named `{slug}`; the plans are {', '.join(names)}.")
    if len(names) == 1:
        return names[0], ""
    plan_lines = [raw.decode("utf-8", errors="replace").split("\n") for raw in sources.values()]
    kinds = {"scope": SCOPE_BLOCK, "tests": TESTS_BLOCK}
    kind = next((name for name, tag in kinds.items() if any(has_block(lines, tag) for lines in plan_lines)), "")
    if kind:
        return None, (f"more than one plan.md exists ({', '.join(names)}) and one holds a {kind} block. The owner "
                      "replies `approve plan <folder>` with the folder name under .sdlc/ of the plan they approve.")
    return None, ""


def refuse(why: str) -> None:
    emit("UserPromptSubmit", system_message=f"sdlc-gate: {why}",
         additionalContext=f"sdlc-gate: {why} Code edits stay locked.")


def plan_limits(root: Path, raw: bytes) -> tuple[list[str] | None, list[str] | None]:
    """(the scope patterns, the frozen test paths) of the plan bytes the approval hashed."""
    text = raw.decode("utf-8", errors="replace")
    globs = parse_scope(text)
    return globs, parse_tests(text, root, globs)


def tests_notice(before: list[str], tests: list[str] | None) -> str:
    """What the approval notice says about frozen tests, to go before the scope list: "" when neither
    approval has any, so a plan with no `sdlc-tests` block reads as it always did. A path that left the
    list comes first, because the owner's `approve plan` is the only thing between an edited plan.md
    and an unfrozen test. Paths are compared as the gate matches them, so a change of case is no change.
    ponytail: a new `/sdlc` in the session drops the old record, and then nothing is "no longer frozen"."""
    now_frozen = tests or []
    old, new = {frozen_key(path) for path in before}, {frozen_key(path) for path in now_frozen}
    removed = sorted(path for path in before if frozen_key(path) not in new)
    added = sorted(path for path in now_frozen if frozen_key(path) not in old) if before else []
    parts = []
    if removed:
        parts.append(f"NO LONGER FROZEN since the last approval: {', '.join(removed)}.")
    if now_frozen:
        parts.append(f"Frozen tests, which only {TESTS_WRITER} may edit: {', '.join(now_frozen)}.")
    if added:
        parts.append(f"Newly frozen since the last approval: {', '.join(added)}.")
    return "".join(f"{part} " for part in parts)


def approval_record(plans: dict, target: str | None, limits: tuple) -> dict:
    """What the approval file holds: the plan hashes, and the scope and frozen tests of the approved plan."""
    globs, tests = limits
    record = {"at": now(), "plans": plans}
    if globs is not None:
        record["scope"] = {"plan": target, "globs": globs}
    if tests is not None:
        record["tests"] = {"plan": target, "paths": tests}
    return record


def announce_approval(line: str, record: dict, frozen_notice: str) -> None:
    scope = record.get("scope")
    limit = frozen_notice + (
        "No `sdlc-scope` block was approved, so edits are not limited to a set of paths." if scope is None
        else f"Edits are limited to {len(scope['globs'])} pattern(s) from {scope['plan']}: {', '.join(scope['globs'])}.")
    emit("UserPromptSubmit", system_message=f"sdlc-gate: plan approved. {limit}", additionalContext=(
        f"sdlc-gate: plan approval recorded: {line}. Bound to: {', '.join(record['plans'])}. {limit} Copy this line "
        "into status.md. A change to any of these plan.md files locks code edits again."))


def approve(data: dict, lock: Path, approved: Path, text: str, slug: str | None = None) -> None:
    waiting_for = intake_pending(data)
    if waiting_for is not None:
        return refuse(intake_refusal(waiting_for))
    root = project_root(data)
    sources = plan_sources(root)
    plans = hash_sources(sources)
    if not plans:
        emit("UserPromptSubmit", additionalContext=(
            "sdlc-gate: no .sdlc/*/plan.md exists yet, so there is no plan to approve and code "
            "edits stay locked. Save plan.md, then ask the owner again."))
        return
    target, globs, tests = None, None, None
    try:
        target, why = choose_plan(sources, slug)
        if why:
            return refuse(why)
        if target:
            globs, tests = plan_limits(root, sources[target])
    except (OSError, ValueError) as exc:
        return refuse(f"{target or 'a plan.md'} cannot be approved: {exc}. Fix the plan, then ask the owner again.")
    record = approval_record(plans, target, (globs, tests))
    frozen_notice = tests_notice(previous_tests(approved), tests)
    line = log_event(data, "approve", text)  # logged before the approval takes effect: a log error leaves the lock on
    log_event(data, "scope", f"{target or 'all plans'} scope={'none' if globs is None else len(globs)}")
    if tests is not None:
        log_event(data, "tests", f"{target} tests={len(tests)}")
    approved.write_text(json.dumps(record))
    lock.unlink(missing_ok=True)
    pin_snyk_base(root)
    announce_approval(line, record, frozen_notice)


def intake_start_note(key: str) -> str:
    held = ("Atlassian writes and every other MCP write are denied until `sdlc off`, and `approve plan` is refused until ")
    if key == NO_KEY:
        return ("sdlc-gate: Jira run, but no ticket key was understood in what the owner typed. " + held
                + "the owner retypes it as `/sdlc jira SCRUM-123` and this session has read that ticket.")
    return (f"sdlc-gate: Jira run for {key}. " + held
            + f"this session has read the ticket with getJiraIssue and its labels hold `{jira_label()}`.")


def intake_refusal(waiting_for: str) -> str:
    if waiting_for == NO_KEY:
        return ("no ticket key was understood in the owner's `/sdlc jira ...`, so no ticket can satisfy the intake: "
                "the owner retypes it, for example `/sdlc jira SCRUM-123`, or replies `sdlc intake off` to go on with no ticket check.")
    return (f"the Jira ticket {waiting_for} has not been read in this session with a `{jira_label()}` label, so there "
            "is no plan to approve. Read it with getJiraIssue, or the owner replies `sdlc intake off` to go on without the label check (MCP writes stay denied).")


def changed_plans(root: Path, approved: Path) -> list[str]:
    recorded = json.loads(approved.read_text()).get("plans", {})
    current = plan_hashes(root)
    return sorted(plan for plan in recorded.keys() | current.keys() if current.get(plan) != recorded.get(plan))


def approved_scope(data: dict) -> list[str] | None:
    """The patterns frozen into this session's approval; None when it is not path-limited."""
    approved = session_file(data, "approved")
    if os.environ.get("SDLC_GATE_SCOPE", "").lower() == "off" or approved is None or not approved.exists():
        return None
    scope = json.loads(approved.read_text()).get("scope")
    if scope is None:
        return None
    globs = scope["globs"]
    if not isinstance(globs, list) or not globs or not all(isinstance(glob, str) for glob in globs):
        raise ValueError("the scope in the gate's record is not a list of patterns")
    return globs
