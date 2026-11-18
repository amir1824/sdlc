"""Reading a Bash command: its statements, its heredocs, and whether it writes a file or the gate's state.
"""
from __future__ import annotations

import bisect
import re

from sdlc_hooks.bash.patterns import AWK_START, AWK_WRITE, COMMIT_MESSAGE, COMMIT_STATEMENT, HEREDOC_HEAD, MAX_CHECKED_COMMAND, QUOTED, SCRATCH_REDIRECT, STATEMENT_END, WRITE_COMMAND
from sdlc_hooks.core.project import CASE_INSENSITIVE_FS
from sdlc_hooks.core.session import state_dir

STATE_FOLDER = ".claude/sdlc-gate"


def unquote(word: str) -> str:
    return word[1:-1] if word[:1] in ("'", '"') else word


def covered(spans: list[tuple[int, int]], position: int) -> bool:
    """Whether position falls inside one of the sorted, non-overlapping spans."""
    index = bisect.bisect_right(spans, (position, float("inf"))) - 1
    return index >= 0 and spans[index][0] <= position < spans[index][1]


def heredoc_spans(command: str) -> list[tuple[int, int, int]]:
    """(head start, body start, body end) of each heredoc. The body runs from the line after `<<WORD`
    to a line holding only WORD, or to the end of the command; the scan never revisits text."""
    spans, position = [], 0
    while True:
        head = HEREDOC_HEAD.search(command, position)
        line_end = command.find("\n", head.end()) if head else -1
        if line_end == -1:
            return spans
        end_line = re.compile(r"^[ \t]*" + re.escape(head.group(2)) + r"[ \t]*$", re.MULTILINE)
        terminator = end_line.search(command, line_end + 1)
        spans.append((head.start(), line_end + 1, terminator.start() if terminator else len(command)))
        position = terminator.end() if terminator else len(command)


def statement_spans(command: str, skip: list[list[tuple[int, int]]]) -> list[tuple[int, int]]:
    """Each statement's span: the text between ;, &&, || and newlines that are not inside a skipped span."""
    cuts = [cut.span() for cut in STATEMENT_END.finditer(command)
            if not any(covered(spans, cut.start()) for spans in skip)]
    return list(zip([0] + [end for _, end in cuts], [start for start, _ in cuts] + [len(command)]))


def without_heredoc_bodies(command: str) -> str:
    """The command with each heredoc body cut out: a body is text for the program that reads it, not a
    command to judge. A shell or interpreter fed a heredoc is caught by its head. A body stays when the
    head pipes it on (`cat <<EOF | sh`), and a `<<` inside quotes is no heredoc."""
    quoted = [quote.span() for quote in QUOTED.finditer(command)]
    kept, position = [], 0
    for head, body_start, body_end in heredoc_spans(command):
        if covered(quoted, head) or "|" in command[head:body_start]:
            continue
        kept.append(command[position:body_start])
        position = body_end
    return "".join(kept) + command[position:]


def writes_files(command: str, scratch_ok: bool = False) -> bool:
    """Whether a command may write; with scratch_ok, a redirect into /tmp does not count."""
    command = without_heredoc_bodies(command)
    bare = re.sub(r"'[^']*'|\"[^\"]*\"", "''", command)
    bare = re.sub(r"(?<!\d)\d?>>?\s*/dev/(?:null|stderr|stdout)|(?<!\d)\d?>&\d", "", bare)
    if scratch_ok:
        bare = SCRATCH_REDIRECT.sub("", bare)
    if ">" in bare or WRITE_COMMAND.search(bare):
        return True
    return bool(AWK_START.search(command) and AWK_WRITE.search(command))


def folded(text: str) -> str:
    return text.casefold() if CASE_INSENSITIVE_FS else text


def spells_state(text: str) -> bool:
    return any(folded(needle) in folded(text) for needle in (STATE_FOLDER, str(state_dir())))


def writes_state(command: str) -> bool:
    """Whether one statement both spells the gate's state folder and writes. A heredoc body and the
    message of a `git commit` are text, so a commit that quotes the folder is not a write to it."""
    visible = COMMIT_STATEMENT.sub(lambda commit: commit["head"] + COMMIT_MESSAGE.sub("-m ''", commit["args"]),
                                   without_heredoc_bodies(command))
    quoted = [quote.span() for quote in QUOTED.finditer(visible)]
    statements = (visible[start:end].strip() for start, end in statement_spans(visible, [quoted]))
    return any(spells_state(statement) and writes_files(statement) for statement in statements)


def too_long(command: str, subject: str) -> str:
    if len(command) <= MAX_CHECKED_COMMAND:
        return ""
    return (f"sdlc-gate: {subject}, and this command is too long to check ({len(command)} characters). "
            "Split it into shorter commands.")
