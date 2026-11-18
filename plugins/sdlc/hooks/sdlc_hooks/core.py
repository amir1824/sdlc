"""What every hook mode shares: where the gate keeps its state, the project, one spelling of a path, the output of a hook
and the approvals log.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")

CASE_INSENSITIVE_FS = sys.platform in ("darwin", "win32")

UNLOCK_WORDS = ("exactly `approve plan` (with more than one plan.md, add the plan's folder name after it), "
                "or `sdlc off` to leave the pipeline")

# An approved scope never covers these, wherever they sit in the tree: they hold the hooks, the
# settings and the tool config that bind the agent.
PROTECTED_NAMES = (".git", ".claude", ".mcp.json")


def gate_home() -> Path:
    return Path(os.environ.get("SDLC_GATE_HOME") or Path.home() / ".claude")


def state_dir() -> Path:
    return gate_home() / "sdlc-gate"


def session_file(data: dict, suffix: str) -> Path | None:
    """The session's state file, or None when the session id is not a safe file name."""
    session_id = str(data.get("session_id", ""))
    return state_dir() / f"{session_id}.{suffix}" if SESSION_ID.fullmatch(session_id) else None


def project_root(data: dict) -> Path:
    return Path(os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."))


def canonical(path: str | Path) -> str:
    """The real path in one spelling: NFC, and case-folded where the filesystem ignores case."""
    real = unicodedata.normalize("NFC", os.path.realpath(path))
    return real.casefold() if CASE_INSENSITIVE_FS else real


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def emit(event: str, system_message: str = "", **fields: str) -> None:
    """The hook's reply: `fields` go to the model; `system_message`, when given, is for the owner."""
    out: dict = {"hookSpecificOutput": {"hookEventName": event, **fields}}
    if system_message:
        out["systemMessage"] = system_message
    print(json.dumps(out, ensure_ascii=False))


def log_event(data: dict, kind: str, text: str) -> str:
    """Append one line to approvals.log and return it."""
    words = json.dumps(text.splitlines()[0][:80], ensure_ascii=False)
    cwd = json.dumps(str(data.get("cwd", "")), ensure_ascii=False)
    line = f"{now()} {kind} session={data.get('session_id')} cwd={cwd} prompt={words}"
    with (state_dir() / "approvals.log").open("a", encoding="utf-8") as log:
        log.write(line + "\n")
    return line


def protected(relative: str) -> bool:
    return any(part in PROTECTED_NAMES for part in relative.split("/"))


def written_relative(data: dict, file_path: str) -> str | None:
    """The path as written, before symlinks are followed, relative to the project by either spelling of
    its root; None when it is not written inside the project."""
    base = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
    written = os.path.abspath(file_path)
    for root in (os.path.abspath(base), os.path.realpath(base)):
        if os.path.commonpath([written, root]) == root:
            return Path(os.path.relpath(written, root)).as_posix()
    return None


def agent_name(data: dict) -> str:
    """The calling agent without its plugin prefix (`sdlc:qa-engineer` and `my-agents:qa-engineer` are one
    role); "" for the main session. ponytail: another plugin's agent of the same name is the same role."""
    return str(data.get("agent_type") or "").split(":")[-1]


def session_gated(data: dict) -> bool:
    """Whether the session has a lock or an approval. Input that cannot name a session is not gated."""
    try:
        files = (session_file(data, "locked"), session_file(data, "approved"))
        return any(path is not None and path.exists() for path in files)
    except (AttributeError, OSError):  # a payload that is not a mapping, or state the hook cannot stat
        return False


def deny(reason: str) -> None:
    emit("PreToolUse", permissionDecision="deny", permissionDecisionReason=reason)


def note_denial(data: dict, kind: str, detail: str) -> None:
    """Log a scope or frozen-test denial after it was emitted, so a failed write cannot drop the denial."""
    try:
        log_event(data, kind, detail)
    except Exception:  # best effort: the denial is already printed
        pass


def trace(mode: str, data: dict) -> None:
    """With SDLC_GATE_TRACE set, record who called the hook, to check what the host sends."""
    fields = ("hook_event_name", "tool_name", "session_id", "agent_id", "agent_type")
    state_dir().mkdir(parents=True, exist_ok=True)
    with (state_dir() / "trace.log").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"mode": mode, **{key: data.get(key) for key in fields}}) + "\n")
