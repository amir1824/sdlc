#!/usr/bin/env python3
"""The sdlc gate hooks for Claude Code: one script, seven hook modes.

The script is only the entry. Each mode is a handler in the `sdlc_hooks` package next to it, imported when that mode
runs, so a call loads only what it needs; the docstring of each module says what its mode does:
  prompt (UserPromptSubmit)                          sdlc_hooks/plan/prompt.py
  tool (PreToolUse)                                  sdlc_hooks/tool.py
  mcp (PreToolUse, matcher `^mcp__`)                 sdlc_hooks/jira/mcp.py
  jira-seen (PostToolUse, the ticket reads)          sdlc_hooks/jira/mcp.py
  snyk-seen (PostToolUse and PostToolUseFailure)     sdlc_hooks/snyk_gate.py
  precompact (PreCompact), compacted (SessionStart)  sdlc_hooks/compact.py
`python3 -I` leaves this folder off sys.path, so the script adds it at the end (the standard library stays first); the
project's own folder is never added.

Fails open, except where an error would lift a limit that is on: a crash of the `tool` hook in a
session that is locked or has an approved plan denies the action (`sdlc off` releases it), and so does
a file path the gate cannot read there. Any other error exits non-zero (never 2), so Claude Code lets
the action through. SDLC_GATE=off disables the gate; SDLC_GATE_SCOPE=off only the scope.
SDLC_GATE_HOME (default ~/.claude) holds sdlc-gate/ and rules/.
ponytail: the gate stops a misread reply and a model's slip, not an agent set on getting past it. A Bash
write is judged by a denylist, so a verb it does not list gets through (a scope pattern is not checked
for Bash); a command that names the gate's state folder and writes is denied, but a path built at run
time is not seen; a run resumed in a new session needs the approval typed again; and input that cannot
name a session fails open. An OS sandbox and a lock keyed by run lift these.
Edits outside CLAUDE_PROJECT_DIR (a sibling package of a larger repo) are never gated.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.append(str(Path(__file__).resolve().parent))


class Mode(NamedTuple):
    """The handler of a hook mode, and what a crash in it means: `holds` is the (module, predicate, situation) of a limit
    that a crash must not lift (the call is denied where the predicate says the limit is on), and `note` is the line
    logged when a PostToolUse hook, which cannot block, fails."""
    module: str
    function: str
    holds: tuple[str, str, str] | None = None
    note: str = ""


MODES = {
    "prompt": Mode("sdlc_hooks.plan.prompt", "on_prompt"),
    "tool": Mode("sdlc_hooks.tool", "on_tool", ("sdlc_hooks.core", "session_gated", "is locked or has an approved plan")),
    "mcp": Mode("sdlc_hooks.jira.mcp", "on_mcp", ("sdlc_hooks.jira.markers", "jira_marker_exists", "has a Jira run")),
    "jira-seen": Mode("sdlc_hooks.jira.mcp", "on_jira_seen", note="jira-seen-error"),  # a failure leaves the intake pending
    "snyk-seen": Mode("sdlc_hooks.snyk_gate", "on_snyk_seen", note="snyk-seen-error"),  # a scan not recorded leaves the gate incomplete
    "precompact": Mode("sdlc_hooks.compact", "on_precompact"),
    "compacted": Mode("sdlc_hooks.compact", "on_compacted"),
}


def handle(mode: Mode, data: dict) -> None:
    """Run the mode's handler. A crash must not open a gate the owner closed: where the mode's limit is on, it denies;
    elsewhere the error propagates and the host lets the call through."""
    try:
        getattr(importlib.import_module(mode.module), mode.function)(data)
    except Exception as error:
        core = importlib.import_module("sdlc_hooks.core")
        if mode.note:
            core.note_denial(data, mode.note, type(error).__name__)
            return
        if mode.holds is None:
            raise
        module, predicate, situation = mode.holds
        if not getattr(importlib.import_module(module), predicate)(data):
            raise
        core.deny(f"sdlc-gate: the gate failed ({type(error).__name__}) while this session {situation}, so it denies "
                  "this action. The owner can reply `sdlc off` to release the session.")


def main() -> int:
    if os.environ.get("SDLC_GATE", "").lower() == "off":
        return 0
    os.umask(0o077)
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    data = json.load(sys.stdin)
    if os.environ.get("SDLC_GATE_TRACE"):
        importlib.import_module("sdlc_hooks.core").trace(name, data)
    if name not in MODES:
        raise ValueError(f"sdlc_gate.py: unknown mode {name!r}; expected 'prompt', 'tool', 'mcp', "
                         "'jira-seen', 'snyk-seen', 'precompact' or 'compacted'")
    handle(MODES[name], data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
