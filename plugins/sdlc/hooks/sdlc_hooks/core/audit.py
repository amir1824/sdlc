"""The approvals log and the trace log: what the gate did, for the owner to read afterwards.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sdlc_hooks.core.session import state_dir


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_event(data: dict, kind: str, text: str) -> str:
    """Append one line to approvals.log and return it."""
    words = json.dumps(text.splitlines()[0][:80], ensure_ascii=False)
    cwd = json.dumps(str(data.get("cwd", "")), ensure_ascii=False)
    line = f"{now()} {kind} session={data.get('session_id')} cwd={cwd} prompt={words}"
    with (state_dir() / "approvals.log").open("a", encoding="utf-8") as log:
        log.write(line + "\n")
    return line


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
