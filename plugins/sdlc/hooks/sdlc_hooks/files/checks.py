"""The checks on an edit with a file tool: the lock, the approved plan, the scope and the frozen tests.
"""
from __future__ import annotations

import os
from pathlib import Path

from sdlc_hooks.core.project import canonical, project_root, protected, written_relative
from sdlc_hooks.core.session import UNLOCK_WORDS, agent_name, session_file, session_gated, state_dir
from sdlc_hooks.plan.approval import approved_scope, changed_plans
from sdlc_hooks.plan.frozen_tests import TESTS_WRITER, approved_tests, frozen_matches
from sdlc_hooks.plan.scope import glob_match

SCOPE_TAG = "sdlc-gate: [scope] "

TESTS_TAG = "sdlc-gate: [tests] "

PATH_KEYS = ("file_path", "notebook_path")


def lock_reason(data: dict, root: Path) -> str:
    lock, approved = session_file(data, "locked"), session_file(data, "approved")
    if lock is not None and lock.exists():
        return ("sdlc-gate: the owner has not approved the plan in this session, so no code is "
                f"written before Build. Ask the owner to reply {UNLOCK_WORDS}. Files under .sdlc/ "
                "stay writable.")
    if approved is None or not approved.exists():
        return ""
    try:
        changed = changed_plans(root, approved)
    except Exception:  # any damage to the record counts as unreadable, and locks
        changed = ["an approved plan.md or the gate's record of it (unreadable)"]
    if changed:
        return (f"sdlc-gate: {', '.join(changed)} changed after the owner approved it, so code "
                f"edits are locked again. Show the owner what changed and ask them to reply {UNLOCK_WORDS}.")
    return ""


def scope_reason(data: dict, relative: str | None) -> str:
    """The reason to deny an edit of `relative` (a path inside the project; None for one that leaves
    it through a symlink), or "". Unlike the rest of the gate it denies when it cannot decide."""
    try:
        globs = approved_scope(data)
        if globs is None:
            return ""
        if relative is not None and not protected(relative) and any(glob_match(glob, relative) for glob in globs):
            return ""
    except Exception as exc:
        return (f"{SCOPE_TAG}the scope check failed ({type(exc).__name__}: {exc}), so this edit is not "
                "allowed. Tell the owner; SDLC_GATE_SCOPE=off turns the scope off.")
    if relative is None:
        return f"{SCOPE_TAG}this path resolves outside the project, which an approved scope does not allow."
    if protected(relative):
        return f"{SCOPE_TAG}{relative} is outside the approved scope: no scope covers .git, .claude or .mcp.json."
    return (f"{SCOPE_TAG}{relative} is outside the approved scope ({', '.join(globs)}). Add it to the "
            f"`sdlc-scope` block of the plan and ask the owner to reply {UNLOCK_WORDS}.")


def frozen_reason(data: dict, spellings: list[str]) -> str:
    """The reason to deny an edit of a frozen reproduction test by anyone but qa-engineer, or "". The
    record is read before the caller is; an unreadable record raises."""
    paths = approved_tests(data)
    if paths is None:
        return ""
    matches = frozen_matches(project_root(data), spellings, paths)
    if not matches or agent_name(data) == TESTS_WRITER:
        return ""
    hit = matches[0][1]
    return (f"{TESTS_TAG}{hit} is a frozen reproduction test of the approved plan, and only {TESTS_WRITER} may "
            f"edit it; this call came from {agent_name(data) or 'the main session'}. If the test is wrong, report "
            f"it and leave it: changing it needs an amended plan.md and the owner's `approve plan`. If you are "
            f"{TESTS_WRITER}, the host did not send your agent type: tell the owner, who can reply `sdlc off`.")


def strict_frozen_reason(data: dict, spellings: list[str]) -> str:
    """frozen_reason that, like the scope, denies when it cannot decide."""
    try:
        return frozen_reason(data, spellings)
    except Exception as exc:
        return (f"{TESTS_TAG}the frozen-tests check failed ({type(exc).__name__}: {exc}), so this edit is not "
                "allowed. Tell the owner, who can reply `sdlc off` to release the session.")


def lenient_frozen_reason(data: dict, spellings: list[str]) -> str:
    """frozen_reason that allows when it cannot decide, for the run's own files."""
    try:
        return frozen_reason(data, spellings)
    except Exception:
        return ""


def file_edit_reason(data: dict, file_path: str) -> str:
    if not file_path:
        return ""
    file_path = os.path.join(str(data.get("cwd") or ""), file_path)
    target, root, state = canonical(file_path), canonical(project_root(data)), canonical(state_dir())
    if os.path.commonpath([target, state]) == state:
        return "sdlc-gate: the gate's state belongs to the owner; do not edit it."
    written = written_relative(data, file_path)
    if os.path.commonpath([target, root]) != root:
        # outside the project nothing is scoped, but a hard link made there to a frozen test is still that test; a path
        # the gate cannot place in the project is never gated when the check fails (the entry's promise)
        return (scope_reason(data, None) or strict_frozen_reason(data, [written])) if written is not None \
            else lenient_frozen_reason(data, [file_path])
    relative = Path(target).relative_to(root)
    spellings = [name for name in (relative.as_posix(), written) if name]
    if relative.parts[:1] == (".sdlc",):
        # A symlink made after approval can lead a frozen name here. The run's own files stay writable
        # when the record cannot be read: the chair must be able to save status.md to say so.
        return lenient_frozen_reason(data, spellings)
    return (lock_reason(data, project_root(data)) or scope_reason(data, relative.as_posix())
            or strict_frozen_reason(data, spellings))


def file_tool_reason(data: dict, tool_input: object) -> tuple[str, str]:
    """(the reason to deny a file tool call, the path it is about), or ("", ""). An input the gate cannot
    read is denied while a run is on: an exception here exits non-zero, which the host reads as allow."""
    try:
        for key in PATH_KEYS:
            path = tool_input.get(key)  # type: ignore[attr-defined]
            if path not in (None, ""):
                reason = file_edit_reason(data, path)
                if reason:
                    return reason, str(path)
    except Exception as exc:
        if not session_gated(data):
            raise
        return (f"sdlc-gate: could not check this path ({type(exc).__name__}: {exc}), so the edit is not "
                "allowed while the plan gate is on. SDLC_GATE=off turns the gate off."), "?"
    return "", ""
