"""The close gate of the Snyk integration, for sdlc_gate.py: whether a write to a run's status.md may close the run or
start Ship while the Security gate is not PASS, and the verdict and the denial text behind it.

Nothing here catches an error: sdlc_gate.py calls it inside one handler that holds the write when Snyk is required.
`host` is the SnykHost sdlc_gate.py builds (see there): the project, the state, and the loader of sibling modules.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import NamedTuple

STATUS_MAX_BYTES = 1 << 20


class ToolCall(NamedTuple):
    data: dict
    tool: str
    tool_input: object


class Scope(NamedTuple):
    """The project the verdict is for: its root, and its record."""
    root: Path
    state: dict


def same_file_as_a_status(host, root: Path, full: str) -> bool:
    """Whether `full` is one of the run folders' status.md under another name (a hard link, a symlink)."""
    if not os.path.exists(full):
        return False
    return any(os.path.samefile(full, status) for status in root.glob(f"{host.load('snyk/close').RUN_FOLDER}/*/status.md"))


def target(host, call: ToolCall) -> Path | None:
    """The file a file tool names when it is a run's status.md under any spelling: written as is or after symlinks,
    in any case, or the same file under another name. None otherwise."""
    path = call.tool_input.get("file_path") if isinstance(call.tool_input, dict) else None
    if not isinstance(path, str) or not path:
        return None
    root = host.root(call.data)
    full = os.path.join(str(call.data.get("cwd") or ""), path)
    is_status = host.load("snyk/close").is_status_relative
    spellings = (host.written_relative(call.data, full), os.path.relpath(os.path.realpath(full), root))
    named = any(spelling and is_status(spelling) for spelling in spellings)
    return Path(full) if named or same_file_as_a_status(host, root, full) else None


def read_status_text(status: Path) -> str | None:
    """The file's text with its line breaks as written (the host matches an edit against them); None when absent.
    A file that is not a regular file, or is large, cannot be read within the hook's time, so it raises."""
    if not status.exists():
        return None
    info = status.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > STATUS_MAX_BYTES:
        raise ValueError(f"a status.md that is not a regular file, or is over {STATUS_MAX_BYTES} bytes")
    with open(status, encoding="utf-8", errors="replace", newline="") as handle:
        return handle.read()


def verdict(host, scope: Scope, budget=None) -> dict:
    """The gate's verdict; the list of changed files and the hash of the code share one time budget, which a command
    that works out the verdict twice passes in so that both runs fit the hook's timeout together."""
    gate, tree = host.load("security_gate"), host.load("snyk/tree")
    base, budget = scope.state.get("base"), budget or tree.new_budget()
    return gate.evaluate(scope.state, gate.Facts(*tree.collect(scope.root, base, budget)))


def denial(host, result: dict, what: str) -> str:
    return (f"{what} is held. {host.load('security_gate').report(result)}\nFix what it names and scan again, or the "
            "owner types: `sdlc snyk accept F<number> <reason>` for a finding, `sdlc snyk waive <reason>` when the scan "
            "could not run, `sdlc snyk off` to stop requiring Snyk in this project.")


def close_reason(host, call: ToolCall, state: dict) -> str:
    """Why this write may not close the run or start Ship, or ""."""
    status = target(host, call)
    if status is None:
        return ""
    current = None if call.tool == "Write" else read_status_text(status)  # a Write leaves nothing of the old text
    if not host.load("snyk/close").closing_after(call.tool, call.tool_input, current):
        return ""
    result = verdict(host, Scope(host.root(call.data), state))
    return "" if result["closable"] else denial(host, result, "closing this run or starting Ship")
