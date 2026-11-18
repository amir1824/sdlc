"""The `sdlc-scope` block of a plan: reading it and matching a path against its patterns.
"""
from __future__ import annotations

import unicodedata

from sdlc_hooks.core import CASE_INSENSITIVE_FS, PROTECTED_NAMES

SCOPE_BLOCK = "sdlc-scope"
SCOPE_MAX_ENTRIES, SCOPE_MAX_ENTRY, SCOPE_MAX_BYTES, SCOPE_MAX_PARTS = 100, 200, 8192, 100

FENCE_MARKS = ("```", "~~~")

# Patterns that match almost all of these are no limit.
# ponytail: a sample test, not a count against the real tree. A list of four or more plain file
# extensions is refused as "nearly every file", and a union of narrow folder patterns (b*/**,
# c*/** ...) can slip under it; the owner reads the frozen list in the approval notice. The upgrade
# is to count matches against `git ls-files` at approval.
BROAD_SAMPLES = ("a/b.txt", "src/x.py", "docs/y.md", "x", "deep/er/path/file.tsx")


def fold(text: str) -> str:
    """One spelling for a path or a pattern: NFC, and case-folded where the filesystem ignores case."""
    text = unicodedata.normalize("NFC", text)
    return text.casefold() if CASE_INSENSITIVE_FS else text


def word_match(pattern: str, word: str) -> bool:
    """One path segment against a pattern whose only wildcards are `*` and `?`; `[` and `]` are
    plain characters. One backtrack point, so the cost is at most len(pattern) * len(word)."""
    i = j = mark = 0
    star = -1
    while j < len(word):
        if i < len(pattern) and pattern[i] == "*":
            star, mark, i = i, j, i + 1
        elif i < len(pattern) and pattern[i] in ("?", word[j]):
            i, j = i + 1, j + 1
        elif star >= 0:
            mark += 1
            i, j = star + 1, mark
        else:
            return False
    return not pattern[i:].strip("*")


def glob_match(glob: str, path: str) -> bool:
    """Whether the `/`-separated path matches the pattern: `*` and `?` inside a segment, and a whole
    `**` segment for any number of segments (a last one needs at least one). Never a regex on the
    path, which an agent chooses: the hook's timeout fails open."""
    pattern, parts = fold(glob).split("/"), fold(path).split("/")
    if len(parts) > SCOPE_MAX_PARTS:
        return False
    failed: set[tuple[int, int]] = set()

    def walk(i: int, j: int) -> bool:
        if (i, j) in failed:
            return False
        if i == len(pattern):
            ok = j == len(parts)
        elif pattern[i] == "**":
            ok = j < len(parts) if i == len(pattern) - 1 else any(walk(i + 1, k) for k in range(j, len(parts) + 1))
        else:
            ok = j < len(parts) and word_match(pattern[i], parts[j]) and walk(i + 1, j + 1)
        if not ok:
            failed.add((i, j))
        return ok

    return walk(0, 0)


def is_broad(globs: list[str]) -> bool:
    """Whether the patterns, taken together, match nearly every path of BROAD_SAMPLES."""
    return sum(any(glob_match(glob, sample) for glob in globs) for sample in BROAD_SAMPLES) >= len(BROAD_SAMPLES) - 1


def check_glob(glob: str) -> None:
    if len(glob) > SCOPE_MAX_ENTRY:
        raise ValueError(f"`{glob[:40]}...` is longer than {SCOPE_MAX_ENTRY} characters")
    if any(unicodedata.category(char) in ("Cc", "Cf", "Zl", "Zp") for char in glob):
        raise ValueError(f"`{glob!r}` has a control or invisible character, which an editor may not show")
    if glob[0] in "/~":
        raise ValueError(f"`{glob}` is an absolute path; write it relative to the project root")
    if "\\" in glob:
        raise ValueError(f"`{glob}` has a backslash; separate folders with /")
    parts = glob.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"`{glob}` has an empty, `.` or `..` segment (a folder is `src/**`, not `src/`)")
    if parts.count("**") > 3:
        raise ValueError(f"`{glob}` has more than 3 `**` segments")
    if is_broad([glob]):
        raise ValueError(f"`{glob}` matches nearly every file, which is no limit")
    if any(part.startswith(".") and word_match(fold(part), name) for part in parts for name in PROTECTED_NAMES):
        raise ValueError(f"`{glob}` reaches .git or .claude (or .mcp.json), which no scope covers")


def opens_fence(line: str, tag: str) -> bool:
    """Whether the line opens a fence that names the tag in any case: `SDLC-TESTS` is a near miss the
    approval refuses, not a block the gate silently ignores."""
    return tag in line.lower() and line.lstrip().startswith(FENCE_MARKS)


def fenced_block(text: str, tag: str) -> list[str] | None:
    """The lines inside the plan's one block fenced with three backticks and `tag`; None when it has
    none; ValueError when what the gate would read could differ from what the owner reads."""
    fence = "```" + tag
    lines = text.split("\n")
    if any(opens_fence(line, tag) and line.rstrip() != fence for line in lines):
        raise ValueError(f"a line opens a code fence for `{tag}` but is not the exact fence: three "
                         f"backticks at the start of the line, then `{tag}`")
    starts = [n for n, line in enumerate(lines) if line.rstrip() == fence]
    if not starts:
        return None
    if len(starts) > 1:
        raise ValueError(f"it holds more than one `{tag}` block")
    # ponytail: counting fence lines, so an unclosed inner fence can fool it; a second block is
    # still refused and the owner reads the frozen list, so it can mis-signal but not widen.
    if sum(line.lstrip().startswith(FENCE_MARKS) for line in lines[:starts[0]]) % 2:
        raise ValueError(f"its `{tag}` block sits inside another code fence")
    body = []
    for line in lines[starts[0] + 1:]:
        if line.rstrip() == "```":
            return body
        body.append(line)
    raise ValueError(f"its `{tag}` block is not closed with ```")


def parse_scope(text: str) -> list[str] | None:
    """The patterns of the plan's one `sdlc-scope` block; None when it has none; ValueError when it
    is malformed or when what the gate would freeze could differ from what the owner reads, so
    approval is refused while a person is watching, not at edit time."""
    body = fenced_block(text, SCOPE_BLOCK)
    if body is None:
        return None
    if len("\n".join(body).encode()) > SCOPE_MAX_BYTES:
        raise ValueError(f"its `sdlc-scope` block is longer than {SCOPE_MAX_BYTES} bytes")
    entries = [line.strip() for line in body]
    globs = [unicodedata.normalize("NFC", entry) for entry in entries if entry and not entry.startswith("#")]
    if not globs:
        raise ValueError("its `sdlc-scope` block is empty")
    if len(globs) > SCOPE_MAX_ENTRIES:
        raise ValueError(f"its `sdlc-scope` block has more than {SCOPE_MAX_ENTRIES} patterns")
    for glob in globs:
        check_glob(glob)
    if is_broad(globs):
        raise ValueError("its patterns together match nearly every file, which is no limit; "
                         "name folders instead of a list of extensions")
    return globs
