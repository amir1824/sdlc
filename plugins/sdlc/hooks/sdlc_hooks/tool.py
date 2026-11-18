"""The `tool` mode: one PreToolUse handler over the file-tool checks, the Bash checks and the Snyk checks.

`tool` (PreToolUse): denies an edit in the project while the session is locked or after an
approved plan.md changed or a new one appeared, an edit outside the frozen scope, a `fix:`
commit without an `Evidence:` line (a message it cannot read is judged on the command text),
a Bash command that writes from a read-only review agent or while the session is locked, and a Bash
command that writes to the gate's state. A plan can also hold an `sdlc-tests` block, the exact paths of a
fix's reproduction tests: the approval freezes them, and afterwards only `qa-engineer` may edit one
with a file tool; the main session and every other agent are denied, also through a symlinked folder
or another case of the name. SDLC_GATE_SCOPE=off does not turn this off. A path that passes through a
symlink, or holds a character outside plain ASCII, is refused at approval.
ponytail: the freeze holds in the session that approved the plan and nowhere else (a second window, or
a resume under a new session id, is not frozen), and it covers the four file tools only. A Bash
write, a script, a formatter, or an edit
of a file the test depends on (a fixture, conftest, test config) still changes what the test proves;
`qa-engineer` may edit a frozen test at any time, so a weakening can be routed through it; another
plugin's agent named `qa-engineer` passes; and the gate cannot see that the test ever failed. /sdlc
has Verify recompute each frozen file's hash against the one recorded after the red run, which finds
these after the fact; an OS sandbox would prevent them.
"""
from __future__ import annotations

import os

from sdlc_hooks.bash.reasons import bash_reason
from sdlc_hooks.core.audit import note_denial
from sdlc_hooks.core.output import deny
from sdlc_hooks.core.project import written_relative
from sdlc_hooks.core.session import agent_name
from sdlc_hooks.files.checks import SCOPE_TAG, TESTS_TAG, file_tool_reason
from sdlc_hooks.snyk_gate import SNYK_TAG, snyk_bash_reason, snyk_close_reason

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def written_path(data: dict, tool_input: object) -> str:
    """The file a file tool names, relative to the project, for the log; `?` when it cannot be told."""
    path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not isinstance(path, str) or not path:
        return "?"
    return written_relative(data, os.path.join(str(data.get("cwd") or ""), path)) or "?"


def on_tool(data: dict) -> None:
    """The Snyk checks run first: an error in an older check lets the host allow the call in a session with no lock,
    and must not lift a limit the owner set with Snyk."""
    tool, tool_input = data.get("tool_name", ""), data.get("tool_input") or {}
    reason, path = "", "?"
    if tool in FILE_TOOLS:
        reason = snyk_close_reason(data, tool, tool_input)
        path = written_path(data, tool_input)
        reason, path = (reason, path) if reason else file_tool_reason(data, tool_input)
    elif tool == "Bash":
        command = str(tool_input.get("command", ""))
        reason = snyk_bash_reason(data, command) or bash_reason(data, command)
        path = (command or "?") if reason.startswith(SNYK_TAG) else "?"
    if reason:
        deny(reason)
        if reason.startswith(SNYK_TAG):
            note_denial(data, "deny-snyk", str(path))
        elif reason.startswith(SCOPE_TAG):
            note_denial(data, "deny-scope", str(path))
        elif reason.startswith(TESTS_TAG):
            note_denial(data, "deny-tests", f"agent={agent_name(data) or 'main'} {path}")
