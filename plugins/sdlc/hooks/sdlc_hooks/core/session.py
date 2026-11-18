"""Where the gate keeps its state, and what a session's files say: the lock, the approval, the calling agent.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")

UNLOCK_WORDS = ("exactly `approve plan` (with more than one plan.md, add the plan's folder name after it), "
                "or `sdlc off` to leave the pipeline")


def gate_home() -> Path:
    return Path(os.environ.get("SDLC_GATE_HOME") or Path.home() / ".claude")


def state_dir() -> Path:
    return gate_home() / "sdlc-gate"


def session_file(data: dict, suffix: str) -> Path | None:
    """The session's state file, or None when the session id is not a safe file name."""
    session_id = str(data.get("session_id", ""))
    return state_dir() / f"{session_id}.{suffix}" if SESSION_ID.fullmatch(session_id) else None


def session_gated(data: dict) -> bool:
    """Whether the session has a lock or an approval. Input that cannot name a session is not gated."""
    try:
        files = (session_file(data, "locked"), session_file(data, "approved"))
        return any(path is not None and path.exists() for path in files)
    except (AttributeError, OSError):  # a payload that is not a mapping, or state the hook cannot stat
        return False


def agent_name(data: dict) -> str:
    """The calling agent without its plugin prefix (`sdlc:qa-engineer` and `my-agents:qa-engineer` are one
    role); "" for the main session. ponytail: another plugin's agent of the same name is the same role."""
    return str(data.get("agent_type") or "").split(":")[-1]
