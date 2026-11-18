"""What a hook says to the host: a reply to the model or the owner, and a denial.
"""
from __future__ import annotations

import json


def emit(event: str, system_message: str = "", **fields: str) -> None:
    """The hook's reply: `fields` go to the model; `system_message`, when given, is for the owner."""
    out: dict = {"hookSpecificOutput": {"hookEventName": event, **fields}}
    if system_message:
        out["systemMessage"] = system_message
    print(json.dumps(out, ensure_ascii=False))


def deny(reason: str) -> None:
    emit("PreToolUse", permissionDecision="deny", permissionDecisionReason=reason)
