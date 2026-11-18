"""The parts of the Snyk close gate that read text, for sdlc_gate.py: whether a write to a run's status.md closes
the run or starts Ship, the text a file tool would leave, and the owner's `sdlc snyk ...` words. No file is
read or written here.

A run is closed when the last line of status.md starts with `closed`, and Ship has started when a stage line
`7 Ship:` is running or done (the format is in commands/sdlc.md, "Status and retro"). An abandoned run needs no gate.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

RUN_FOLDER = ".sdlc"
SHIP_STARTED = re.compile(r"7 Ship: (?:running|done)\b")
OWNER_COMMAND = re.compile(r"sdlc snyk (?P<verb>on|off|accept|waive)(?: (?P<rest>.+))?", re.IGNORECASE | re.DOTALL)
FINDING_SHORT_ID = re.compile(r"F[0-9]{1,4}")
QUOTE_FOLDING = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})


def is_closing(text: str) -> bool:
    """Lines are split and stripped as status_check.py reads them, so no spelling the parser accepts is missed."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return (bool(lines) and lines[-1].startswith("closed")) or any(SHIP_STARTED.match(line) for line in lines)


def is_status_relative(relative: str) -> bool:
    """Whether a path relative to the project is `<run folder>/<run>/status.md`, in any case: the file system may not tell
    the spellings apart."""
    parts = PurePosixPath(relative.casefold()).parts
    return len(parts) == 3 and parts[0] == RUN_FOLDER and parts[2] == "status.md"


def resulting_text(tool: str, tool_input: dict, current: str | None) -> str | None:
    """The text a Write, Edit or MultiEdit leaves in the file. None when the edit cannot apply (the host
    refuses it). ValueError when the input is not the shape of one of those tools."""
    if tool == "Write":
        content = tool_input.get("content")
        if not isinstance(content, str):
            raise ValueError("a Write with no text")
        return content
    edits = [tool_input] if tool == "Edit" else tool_input.get("edits") if tool == "MultiEdit" else None
    if not isinstance(edits, list) or not edits:
        raise ValueError(f"{tool} is not an edit of a file")
    text = current
    for edit in edits:
        if not (isinstance(edit.get("old_string"), str) and isinstance(edit.get("new_string"), str)):
            raise ValueError("an edit whose strings are not text")
        text = apply_edit(text, edit)
        if text is None:
            return None
    return text


def closing_after(tool: str, tool_input: dict, current: str | None) -> bool:
    """Whether the write may close the run. An edit that cannot apply to a file that is there is held, whatever it
    says: the host may match what this read did not (line breaks, quotes), and a deletion can close a run too. The
    host refuses an edit that really does not apply, so holding it costs nothing. An edit of a file that is not there
    is judged by its new text."""
    text = resulting_text(tool, tool_input, current)
    if text is not None:
        return is_closing(text)
    edits = [tool_input] if tool == "Edit" else tool_input["edits"]
    return current is not None or any(
        isinstance(edit.get("new_string"), str) and is_closing(edit["new_string"]) for edit in edits)


def apply_edit(text: str | None, edit: dict) -> str | None:
    """The text after one edit; None when it cannot apply. An empty `old` on a file that is not there creates it, and
    a match the host may make after folding curly quotes to straight ones is found the same way."""
    old, new, replace_all = edit["old_string"], edit["new_string"], edit.get("replace_all") is True
    if text is None:
        return new if old == "" else None
    if old not in text:
        folded, old = text.translate(QUOTE_FOLDING), old.translate(QUOTE_FOLDING)
        if old not in folded:
            return None
        text = folded
    return text.replace(old, new) if replace_all else text.replace(old, new, 1)


def parse_command(text: str) -> tuple[str, str] | None:
    """(verb, the words after it) for exactly `sdlc snyk on|off|accept|waive ...`, else None. With a slash it is the
    host's /sdlc command, which starts a run, so it is not this one."""
    found = OWNER_COMMAND.fullmatch(text.strip())
    return (found.group("verb").lower(), (found.group("rest") or "").strip()) if found else None


def accept_args(words: str) -> tuple[str, str] | None:
    """(finding, reason) from `F2 the reason`; None when either is missing."""
    parts = words.split(None, 1)
    return (parts[0], parts[1].strip()) if len(parts) == 2 and FINDING_SHORT_ID.fullmatch(parts[0]) else None
