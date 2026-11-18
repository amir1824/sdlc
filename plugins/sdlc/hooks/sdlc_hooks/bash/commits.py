"""The `Evidence:` line a `fix:` commit needs, judged from the command and the message it can read.
"""
from __future__ import annotations

import bisect
import itertools
import os
import re
from pathlib import Path

from sdlc_hooks.bash.parse import covered, heredoc_spans, statement_spans, unquote
from sdlc_hooks.bash.patterns import CD, EVIDENCE_LINE, EVIDENCE_REASON, FIX_SUBJECT, GIT_COMMIT, GIT_DIR, HEREDOC_START, INLINE_HEREDOC, LOOSE_EVIDENCE, LOOSE_FIX, MAX_COMMITS, MESSAGE_FILE, MESSAGE_FLAG, QUOTED

def commit_dir(command: str, commit: re.Match, cwd: str, text: list[list[tuple[int, int]]]) -> Path:
    """Where a commit runs: the session's cwd, then each `cd` before it that is not text (quoted or in a
    heredoc body), then its `git -C`."""
    cds = [cd.group(1) for cd in CD.finditer(command, 0, commit.start())
           if not any(covered(spans, cd.end() - 1) for spans in text)]
    directory = Path(cwd or ".")
    for target in cds + GIT_DIR.findall(commit.group(0)):
        directory = directory / os.path.expanduser(unquote(target))
    return directory


def message_source(command: str, commit: re.Match, message_file: str, statements: list[tuple[int, int]]) -> str:
    """The text that supplies a message the gate cannot read: the commit's own statement for `-F -` (the
    pipe into it, a heredoc after it), or the statements before it that write its -F file."""
    if message_file == "-":
        start, end = statements[bisect.bisect_right(statements, (commit.end(), float("inf"))) - 1]
        return command[start:end]
    writes = re.compile(r"(?:>>?|\btee\b(?:[ \t]+-a)?)[ \t]*['\"]?" + re.escape(message_file) + r"['\"]?(?![\w./-])")
    return "\n".join(command[start:end] for start, end in statements
                     if end <= commit.start() and writes.search(command, start, end))


def commit_message(args: str, directory: Path) -> str | None:
    """The message from -F <file>, -F - with a heredoc, or -m; None when -F names one the gate cannot read."""
    message_file = MESSAGE_FILE.search(args)
    if message_file and unquote(message_file.group(1)) != "-":
        path = directory / os.path.expanduser(unquote(message_file.group(1)))
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
    if message_file:
        heredoc = HEREDOC_START.search(args)
        return args[heredoc.end():] if heredoc else None
    flag = MESSAGE_FLAG.search(args)
    rest = args[flag.end():] if flag else ""
    inline = INLINE_HEREDOC.match(rest)
    return rest[inline.end():] if inline else rest


def commit_reason(command: str, cwd: str) -> str:
    """The reason to deny a fix: commit in the command that has no Evidence: line, or ""."""
    commits = list(itertools.islice(GIT_COMMIT.finditer(command), MAX_COMMITS + 1))
    if not commits:
        return ""
    if len(commits) > MAX_COMMITS:
        return f"sdlc-gate: this command holds more than {MAX_COMMITS} git commits, too many to check. Split it."
    heredocs = heredoc_spans(command)
    bodies = [(body_start, body_end) for _, body_start, body_end in heredocs]
    quoted = [quote.span() for quote in QUOTED.finditer(command)]
    statements = statement_spans(command, [quoted, [(head, body_end) for head, _, body_end in heredocs]])
    commits = [commit for commit in commits if not covered(bodies, commit.end() - 1)]
    ends = [commit.start() for commit in commits[1:]] + [len(command)]
    for commit, end in zip(commits, ends):
        args = command[commit.end():end]
        message = commit_message(args, commit_dir(command, commit, cwd, [quoted, bodies]))
        if message is None:
            source = message_source(command, commit, unquote(MESSAGE_FILE.search(args).group(1)), statements)
            unchecked = LOOSE_FIX.search(source) and not LOOSE_EVIDENCE.search(source)
        else:
            subject = message.strip().splitlines()[0].strip() if message.strip() else ""
            unchecked = FIX_SUBJECT.match(subject) and not EVIDENCE_LINE.search(message)
        if unchecked:
            return EVIDENCE_REASON
    return ""
