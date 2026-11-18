"""The baseline of a frozen reproduction test, and the command that compares it with the file now.

`frozen-seen` (PostToolUse on Edit, Write, MultiEdit and NotebookEdit): when the file written is a frozen test of this session's
approval, its content hash is recorded in `sdlc-gate/frozen/<project>.json`. PreToolUse denies the write of a frozen
file to everyone but qa-engineer, so a write that reaches PostToolUse is qa-engineer's; a call that names another agent
records nothing (a denial that was skipped must not become the baseline), and one that names none is recorded.
`unreadable` joins the status words. Writers of the record hold a `flock` on its folder.
At the approval (`record_approved_tests`, the owner's words) every frozen path gets a line: the content of a file that
already exists, unless an earlier approval recorded one, or "" for one qa-engineer has not written yet.
`frozen-status` (run by hand, no input): one line per frozen test, `ok`, `CHANGED`, `missing`, `unreadable` or `NO BASELINE`. The
record sits in the gate's state folder, which Bash may not write, so a builder cannot make it agree with an edit the
way it could with the Red run rows of `build.md`.
ponytail: qa-engineer writing a file after someone changed it with Bash records the changed content; the upgrade is
to compare the file with the last baseline at PreToolUse. The record is per project, not per run, and holds the paths
of the current approval only, so a file that was changed on purpose between two runs that freeze it shows CHANGED until
`qa-engineer` writes it again.
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # no flock (Windows): ponytail: two parallel writes of frozen tests can lose a baseline line
    fcntl = None

from sdlc_hooks.core.project import canonical, project_root, written_relative
from sdlc_hooks.core.session import agent_name, state_dir
from sdlc_hooks.files.checks import PATH_KEYS
from sdlc_hooks.plan.frozen_tests import TESTS_WRITER, approved_tests, frozen_matches

RECORD_KEY_CHARS = 32
HASH_SHOWN = 12
UNREADABLE = ("frozen tests: the record cannot be read; the owner can delete it, and the next write of a frozen "
              "test records it again")


def record_path(root: Path) -> Path:
    return state_dir() / "frozen" / f"{hashlib.sha256(canonical(root).encode()).hexdigest()[:RECORD_KEY_CHARS]}.json"


def content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_record(path: Path) -> dict[str, str] | None:
    """The recorded hashes by frozen path: {} when there is no record, None when it cannot be read."""
    try:
        loaded = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except Exception:  # noqa: BLE001 - OSError, bad JSON or nesting too deep all mean the same: not readable
        return None
    ok = isinstance(loaded, dict) and all(isinstance(key, str) and isinstance(value, str) for key, value in loaded.items())
    return loaded if ok else None


def write_record(path: Path, record: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(record))
    os.replace(temp, path)


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Holds a lock on the record's folder for a read-modify-write, so two writes at once keep both lines. The folder
    is locked, not a file beside the record, so no second file is left behind (ponytail: it serialises every project's
    writes, which are a few milliseconds)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        if fcntl:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def record_approved_tests(root: Path, paths: list[str]) -> None:
    """At a plan approval: one baseline line per frozen path (see the module's docstring); nothing is written for a plan
    with no frozen tests and no earlier record."""
    path = record_path(root)
    if not paths and not path.exists():
        return
    with locked(path):
        earlier = read_record(path)
        if earlier is None:
            return  # a record that cannot be read stays so, and `frozen-status` says it: re-baselining would hide a change
        write_record(path, {name: earlier.get(name) or (content_hash(root / name) if (root / name).is_file() else "")
                            for name in paths})


def spellings_of(data: dict, file_path: str) -> list[str]:
    """The names a written path goes by in the project: after symlinks, and as written."""
    full = os.path.join(str(data.get("cwd") or ""), file_path)
    target, root = canonical(full), canonical(project_root(data))
    inside = os.path.commonpath([target, root]) == root
    names = (Path(target).relative_to(root).as_posix() if inside else None, written_relative(data, full))
    return [name for name in names if name]


def frozen_files_written(data: dict, paths: list[str]) -> set[str]:
    """The frozen tests (as the plan spells them) that this file tool call wrote."""
    tool_input = data.get("tool_input")
    named = [tool_input[key] for key in PATH_KEYS if isinstance(tool_input, dict) and tool_input.get(key)]
    spellings = [spelling for name in named for spelling in spellings_of(data, name)]
    return {path for path, _ in frozen_matches(project_root(data), spellings, paths)}


def on_frozen_seen(data: dict) -> None:
    """PostToolUse: record the hash of each frozen test this call wrote. Advisory: an error is logged by the entry and
    never blocks the write. A call that names another agent than qa-engineer records nothing: PreToolUse should have
    denied it, and a baseline taken from it would hide the change."""
    paths = approved_tests(data)
    if paths is None or agent_name(data) not in ("", TESTS_WRITER):
        return
    written = frozen_files_written(data, paths)
    if not written:
        return
    root = project_root(data)
    with locked(record_path(root)):
        kept = {path: hash_ for path, hash_ in (read_record(record_path(root)) or {}).items() if path in paths}
        kept.update({path: content_hash(root / path) for path in written if (root / path).is_file()})
        write_record(record_path(root), kept)


def file_state(recorded: str, now: str | None) -> str:
    if not recorded:
        return "NO BASELINE"
    if now is None:
        return "missing"
    if now == "unreadable":
        return "unreadable"
    return "ok" if now == recorded else "CHANGED"


def current_hash(file: Path) -> str | None:
    """The file's hash now; None when it is gone, and "unreadable" when it cannot be read."""
    try:
        return content_hash(file) if file.is_file() else None
    except OSError:
        return "unreadable"


def status_line(root: Path, path: str, recorded: str) -> str:
    now = current_hash(root / path)
    return f"{path} {file_state(recorded, now)} (recorded {recorded[:HASH_SHOWN] or '-'}, now {now[:HASH_SHOWN] if now else '-'})"


def project_with_record(start: Path) -> Path:
    """The folder, `start` or one above it, whose project has a record: a Bash command may run in a subfolder."""
    return next((folder for folder in (start, *start.parents) if record_path(folder).exists()), start)


def status_lines(root: Path) -> list[str]:
    recorded = read_record(record_path(root))
    if recorded is None:
        return [UNREADABLE]
    if not recorded:
        return ["frozen tests: none recorded for this project"]
    return [status_line(root, path, hash_) for path, hash_ in sorted(recorded.items())]


def print_status() -> int:
    """`sdlc_gate.py frozen-status`: for the project of the current folder (or CLAUDE_PROJECT_DIR), read only."""
    if os.environ.get("SDLC_GATE", "").lower() == "off":
        print("frozen tests: the gate is off, so no baseline is being recorded")
        return 0
    print("\n".join(status_lines(project_with_record(project_root({"cwd": os.getcwd()})))))
    return 0
