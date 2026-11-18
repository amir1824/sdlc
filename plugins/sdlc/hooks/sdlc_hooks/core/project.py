"""Where the project is and how a path of it is spelled: its root, one spelling of a path, and the names an
approved scope never covers.
"""
from __future__ import annotations

import os
import sys
import unicodedata
from pathlib import Path

CASE_INSENSITIVE_FS = sys.platform in ("darwin", "win32")

# An approved scope never covers these, wherever they sit in the tree: they hold the hooks, the
# settings and the tool config that bind the agent.
PROTECTED_NAMES = (".git", ".claude", ".mcp.json")


def project_root(data: dict) -> Path:
    return Path(os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."))


def canonical(path: str | Path) -> str:
    """The real path in one spelling: NFC, and case-folded where the filesystem ignores case."""
    real = unicodedata.normalize("NFC", os.path.realpath(path))
    return real.casefold() if CASE_INSENSITIVE_FS else real


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
