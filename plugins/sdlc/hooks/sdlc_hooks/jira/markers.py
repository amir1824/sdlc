"""The marker of a session with a Jira run, and the intake that waits for the ticket's label.
"""
from __future__ import annotations

import os
import re

from sdlc_hooks.core import project_root, session_file, session_gated

JIRA_KEY = re.compile(r"[A-Z][A-Z0-9_]{1,30}-[0-9]{1,9}")
JIRA_RUN_KEY = re.compile(r"/(?:[\w-]+:)?sdlc\s+(?:(?:lean|full)\s+)?(?:jira\s+(?P<key>\S+)|resume\s+jira-(?P<slug>\S+))",
                          re.IGNORECASE)
NO_KEY = "?"  # what an armed intake waits for when no key was understood: no response key can equal it

# A token after `jira` that was meant as a key or a link (SCRUM-１, a browse URL) but was not understood arms the
# intake with NO_KEY; ordinary words (`/sdlc jira dashboard for the team`) are an ordinary request.
JIRA_ATTEMPT = re.compile(r"[A-Za-z][A-Za-z0-9_]*-\S*\d|atlassian\.net", re.IGNORECASE)
JIRA_LABEL_DEFAULT = "sdlc"

# In a Jira run an MCP tool is allowed only when its name, split into words (getJiraIssue,
# jira_get_issue), starts with a read verb and holds no write word: `getOrCreateJiraIssue` is a write.
NAME_WORDS = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|[0-9]+")


def jira_marker_exists(data: dict) -> bool:
    try:
        marker = session_file(data, "jira")
        return marker is not None and marker.exists()
    except OSError:  # state the hook cannot stat: no marker is seen, as with the lock
        return False


def mark_jira(data: dict) -> None:
    """Write the session's Jira marker: its existence is all that is read."""
    marker = session_file(data, "jira")
    if marker is not None:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()


def run_key(text: str) -> str:
    """The ticket key in what the owner typed after `/sdlc jira` or `/sdlc resume jira-`, upper case, or ""."""
    run = JIRA_RUN_KEY.match(text)
    token = ((run.group("key") or run.group("slug")) if run else "").upper()
    if "://" in token:  # the host name can look like a key (ACME-2.atlassian.net): only what follows /browse/ counts
        token = token.partition("/BROWSE/")[2]
    found = JIRA_KEY.search(token)
    return found.group(0) if found else ""


def jira_request(text: str) -> str | None:
    """The key of a typed `/sdlc jira KEY` or `/sdlc resume jira-key`, NO_KEY when the token looks like a key or a
    link that was not understood, or None when the prompt is not a Jira run."""
    run = JIRA_RUN_KEY.match(text)
    if not run:
        return None
    attempt = run.group("slug") is not None or JIRA_ATTEMPT.search(run.group("key") or "")
    return run_key(text) or (NO_KEY if attempt else None)


def jira_label() -> str:
    return os.environ.get("SDLC_JIRA_LABEL") or JIRA_LABEL_DEFAULT


def arm_intake(data: dict, key: str) -> None:
    """From now `approve plan` is refused until this session has read the ticket and seen its label."""
    pending = session_file(data, "jira-intake")
    if pending is not None:
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text(key)


def intake_pending(data: dict) -> str | None:
    """The key a pending intake waits for (NO_KEY when none was understood), or None when nothing is pending."""
    pending = session_file(data, "jira-intake")
    if pending is None or not pending.exists():
        return None
    waiting_for = pending.read_text(errors="replace")
    return waiting_for if JIRA_KEY.fullmatch(waiting_for) else NO_KEY


def gated_session_with_jira_run(data: dict) -> bool:
    """Whether a gated session's project holds a Jira run folder, even a closed one."""
    return session_gated(data) and any(path.is_dir() for path in project_root(data).glob(".sdlc/jira-*"))


def words_of(name: str) -> list[str]:
    return [word.lower() for word in NAME_WORDS.findall(name)]
