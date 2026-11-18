"""The `sdlc-tests` block of a plan: the reproduction tests an approval freezes.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

from sdlc_hooks.core.session import session_file
from sdlc_hooks.plan.scope import SCOPE_BLOCK, check_glob, fenced_block, glob_match, opens_fence

TESTS_BLOCK, TESTS_MAX_ENTRIES, TESTS_WRITER = "sdlc-tests", 20, "qa-engineer"

WILDCARDS = "*?"

# An exact path is matched as text, so `[id]` is a plain name; a letter from another alphabet that looks
# like an ASCII one would freeze a name no file has, and the owner could not tell it apart in the notice.
TEST_PATH = re.compile(r"[A-Za-z0-9 ._/@+=,()\[\]-]+")


def frozen_key(path: str) -> str:
    """One spelling for a frozen test's path. Always case-folded: a mount can ignore case on any platform,
    and treating two names that differ only in case as one file only denies more."""
    return unicodedata.normalize("NFC", path).casefold()


def check_test_path(path: str, root: Path) -> None:
    if any(char in path for char in WILDCARDS):
        raise ValueError(f"`{path}` has a wildcard; a line of `{TESTS_BLOCK}` is one exact file")
    check_glob(path)
    if not TEST_PATH.fullmatch(path):
        raise ValueError(f"`{path!r}` has a character outside ASCII letters, digits, space and ._-/@+=,()[] ; "
                         "a look-alike letter would freeze a name no file has")
    if frozen_key(path.split("/")[0]) == ".sdlc":
        raise ValueError(f"`{path}` is under .sdlc/, which holds the run's own files")
    if (root / path).is_dir():
        raise ValueError(f"`{path}` is a folder; a line of `{TESTS_BLOCK}` is one exact file")
    if Path(os.path.realpath(root / path)) != root / path:
        raise ValueError(f"`{path}` passes through a symlink; name the real file")


def parse_tests(text: str, root: Path, globs: list[str] | None) -> list[str] | None:
    """The exact paths of the plan's one `sdlc-tests` block; None when it has none; ValueError when it is
    malformed, or names a file the approved scope would not let anyone write."""
    body = fenced_block(text, TESTS_BLOCK)
    if body is None:
        return None
    entries = [line.strip() for line in body]
    paths = [unicodedata.normalize("NFC", entry) for entry in entries if entry and not entry.startswith("#")]
    if not paths:
        raise ValueError(f"its `{TESTS_BLOCK}` block is empty")
    if len(paths) > TESTS_MAX_ENTRIES:
        raise ValueError(f"its `{TESTS_BLOCK}` block has more than {TESTS_MAX_ENTRIES} paths")
    if len({frozen_key(path) for path in paths}) != len(paths):
        raise ValueError(f"its `{TESTS_BLOCK}` block names a file twice")
    for path in paths:
        check_test_path(path, root)
        if globs is not None and not any(glob_match(glob, path) for glob in globs):
            raise ValueError(f"`{path}` is in `{TESTS_BLOCK}` but outside the `{SCOPE_BLOCK}` block, so nobody "
                             "could write it")
    return paths


def has_block(lines: list[str], tag: str) -> bool:
    """Whether the plan's lines hold a block with this tag or a fence that looks like one (fenced_block refuses it)."""
    return any(opens_fence(line, tag) for line in lines)


def previous_tests(approved: Path) -> list[str]:
    """The frozen paths of the approval this one replaces, for the notice only: unreadable counts as none."""
    try:
        record = json.loads(approved.read_text())
    except (OSError, ValueError):
        return []
    tests = record.get("tests") if isinstance(record, dict) else None
    paths = tests.get("paths") if isinstance(tests, dict) else None
    return [path for path in paths if isinstance(path, str)] if isinstance(paths, list) else []


def approved_tests(data: dict) -> list[str] | None:
    """The frozen test paths of this session's approval; None when it holds none."""
    approved = session_file(data, "approved")
    if approved is None or not approved.exists():
        return None
    tests = json.loads(approved.read_text()).get("tests")
    if tests is None:
        return None
    paths = tests["paths"]
    if not isinstance(paths, list) or not paths or not all(isinstance(path, str) for path in paths):
        raise ValueError("the frozen tests in the gate's record are not a list of paths")
    return paths


def frozen_keys(root: Path, paths: list[str]) -> set[str]:
    """Each frozen path as the plan spells it and as it resolves, so an edit through a symlinked folder,
    or of the file a frozen symlink points at, is the same file."""
    keys = {frozen_key(path) for path in paths}
    for path in paths:
        resolved = os.path.realpath(root / path)
        if os.path.commonpath([resolved, str(root)]) == str(root):
            keys.add(frozen_key(Path(os.path.relpath(resolved, root)).as_posix()))
    return keys
