#!/usr/bin/env python3
"""The sdlc gate hooks for Claude Code: one script, two hook events.

`prompt` (UserPromptSubmit): a typed `/sdlc` locks code edits in that session; a reply of
exactly `approve plan` or `אשר תוכנית` unlocks them and binds the approval to the hash of
each `.sdlc/*/plan.md`; a reply of exactly `sdlc off` releases the session.
`tool` (PreToolUse): denies an edit in the project while the session is locked or after an
approved plan.md changed or a new one appeared, a `fix:` commit without an `Evidence:` line
(a message it cannot read is judged on the command text), and a Bash command that writes from a
read-only review agent.

Fails open: any error exits non-zero (never 2), so Claude Code lets the action through.
SDLC_GATE=off disables it. SDLC_GATE_HOME (default ~/.claude) holds sdlc-gate/ and rules/.
ponytail: the gate stops a misread reply, not an agent set on getting past it. Bash writes
in a locked session are not gated, Bash can delete the gate's state, and a run resumed in
a new session needs the approval typed again; an OS sandbox and a lock keyed by run lift these.
One file over the 200-line limit on purpose: `python3 -I` drops this folder from sys.path,
so a second module would need path hacking to import.
"""
from __future__ import annotations

import bisect
import hashlib
import itertools
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

SDLC_PROMPT = re.compile(r"/(?:[\w-]+:)?sdlc(?:\s|$)")
APPROVE_PROMPT = re.compile(r"(?:approve plan|אשר תוכנית)[\s.!]*", re.IGNORECASE)
RELEASE_PROMPT = re.compile(r"/?sdlc off[\s.!]*", re.IGNORECASE)
SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_ONLY_AGENTS = {"tech-lead", "security-reviewer", "brutal-reviewer", "analyst", "leak-scanner"}
# Every command pattern below is linear: a separator or a newline ends any repeat, so a
# hostile command cannot run the hook past its timeout (which fails open).
COMMAND_START = r"(?:^|[;&|\n`(\"'][ \t]*)"
VERB_END = r"(?=\s|$|[;&|)])"
SPACE = r"[ \t]+"
WORD = r"[^\s;&|]"
BINARY_PATH = r"(?:[\w.~/-]*/)?"
QUOTES = r"(?:\\?['\"])*"
GIT = (BINARY_PATH + r"git" + SPACE + r"(?:(?:-[Cc]" + SPACE + r"(?:\"[^\"\n]{0,256}\"|'[^'\n]{0,256}'|"
       + r"[^\s;&|'\"]+)|--[\w-]+(?:=" + WORD + r"+)?)" + SPACE + r")*")
MAX_CHECKED_COMMAND = 16_000
CASE_INSENSITIVE_FS = sys.platform in ("darwin", "win32")
# ponytail: a denylist of the common ways to write, not a sandbox. `python3 -c`, `$(...)`, a
# quoted verb, an interpreter fed a here-doc and any verb not listed get through; an OS
# sandbox is the upgrade.
WRITE_COMMAND = re.compile(
    COMMAND_START + r"(?:(?:sudo|time|nohup|command|exec|then|do|else)" + SPACE + r")*"
    + r"(?:env" + SPACE + r"(?:\w+=" + WORD + r"*" + SPACE + r")*)?"
    + r"(?:xargs" + SPACE + r"(?:-" + WORD + r"+" + SPACE + r")*)?\\?" + BINARY_PATH
    + r"(?:rm|rmdir|mv|cp|tee|touch|mkdir|chmod|chown|ln|truncate|dd|eval)" + VERB_END
    + r"|" + COMMAND_START + BINARY_PATH + r"(?:ba|z)?sh" + SPACE + r"(?:-" + WORD + r"+" + SPACE + r")*-c"
    + VERB_END
    + r"|" + COMMAND_START + BINARY_PATH + r"sed" + SPACE + r"(?:" + WORD + r"+" + SPACE + r")*?(?:-i|--in-place)"
    + r"|" + COMMAND_START + BINARY_PATH + r"perl" + SPACE + r"(?:" + WORD + r"+" + SPACE + r")*?-\w*i"
    + r"|" + COMMAND_START + GIT + r"(?:commit|push|pull|reset|checkout|switch|restore|rebase|merge"
    + r"|cherry-pick|clean|apply|am|add|rm|mv|init|clone|fetch|worktree|update-ref|config|gc|prune)" + VERB_END
    + r"|" + COMMAND_START + GIT + r"(?:stash(?![ \t]+(?:list|show)\b)"
    + r"|tag" + SPACE + r"(?!-l\b|--list\b|--contains\b|-n\b)" + WORD
    + r"|branch" + SPACE + r"(?:(?!-)" + WORD + r"|(?:" + WORD + r"+" + SPACE + r")*?-(?:[a-zA-Z]*[dDmMcCfut]"
    + r"|-(?:delete|move|copy|force|track|set-upstream-to|unset-upstream|edit-description)\b)))"
    + r"|" + COMMAND_START + r"(?:npm|pnpm|yarn|pip3?|brew|uv)" + SPACE
    + r"(?:install|i|ci|add|remove|uninstall)" + VERB_END
    + r"|" + COMMAND_START + r"(?:curl|wget)\b[^;&|\n]*[ \t](?:-o|-O|--output)\b"
    + r"|[ \t]-(?:delete|exec)\b"
)
GIT_COMMIT = re.compile(COMMAND_START + r"(?:\w+=" + WORD + r"*" + SPACE + r")*" + GIT + r"commit\b")
QUOTED_OR_WORD = r"(\"[^\"\n]*\"|'[^'\n]*'|[^\s;&|)'\"]+)"
MESSAGE_FILE = re.compile(r"(?:[ \t]-F|--file)(?:=|[ \t]+)" + QUOTED_OR_WORD)
CD = re.compile(r"(?:^|[;&|\n(][ \t]*)cd" + SPACE + QUOTED_OR_WORD)
GIT_DIR = re.compile(r"[ \t]-C" + SPACE + QUOTED_OR_WORD)
MESSAGE_FLAG = re.compile(r"(?:[ \t]-[a-zA-Z]*m|--message)(?:=|[ \t]*)" + QUOTES)
HEREDOC_START = re.compile(r"<<-?[ \t]*['\"]?\w{1,64}['\"]?[^\n]{0,256}\n")
INLINE_HEREDOC = re.compile(r"\$\([ \t]*cat[ \t]*<<-?[ \t]*['\"]?\w+['\"]?[^\n]*\n")
FIX_SUBJECT = re.compile(r"fix(?:\([^)]*\))?!?:", re.IGNORECASE)
EVIDENCE_LINE = re.compile(r"(?:^|\n|-m[ \t]*" + QUOTES + r"|--message=" + QUOTES + r")[ \t]*Evidence:[ \t]*[^\s'\"\\]")
# For a message the gate cannot read (piped in, or a -F file not there yet): the same two checks
# on the text that supplies it, at a line start, an escaped `\n` or a quote.
LOOSE_FIX = re.compile(r"(?:^|\n|\\n|['\"])[ \t]*fix(?:\([^)\n]{0,64}\))?!?:", re.IGNORECASE)
LOOSE_EVIDENCE = re.compile(r"(?:^|\n|\\n|['\"])[ \t]*Evidence:[ \t]*[^\s'\"\\]")
# A heredoc's head only: its body is found by scanning lines (heredoc_spans), which a single regex
# with a lazy body would do in quadratic time on an unterminated head.
HEREDOC_HEAD = re.compile(r"(?<![<\d])<<(?!<)-?[ \t]*(['\"]?)([A-Za-z_]\w{0,63})\1")
QUOTED = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"")
STATEMENT_END = re.compile(r";|&&|\|\||(?<!\\)\n")
MAX_COMMITS = 50
EVIDENCE_REASON = ("sdlc-gate: a fix: commit needs an `Evidence:` line in its body: a log line quoted with its "
                   "file and line, or the name of a check that failed before the change. "
                   "Write only evidence you observed.")
UNLOCK_WORDS = "exactly `approve plan` (or `אשר תוכנית`), or `sdlc off` to leave the pipeline"


def gate_home() -> Path:
    return Path(os.environ.get("SDLC_GATE_HOME") or Path.home() / ".claude")


def state_dir() -> Path:
    return gate_home() / "sdlc-gate"


def session_file(data: dict, suffix: str) -> Path | None:
    """The session's state file, or None when the session id is not a safe file name."""
    session_id = str(data.get("session_id", ""))
    return state_dir() / f"{session_id}.{suffix}" if SESSION_ID.fullmatch(session_id) else None


def project_root(data: dict) -> Path:
    return Path(os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."))


def canonical(path: str | Path) -> str:
    """The real path in one spelling: NFC, and case-folded where the filesystem ignores case."""
    real = unicodedata.normalize("NFC", os.path.realpath(path))
    return real.casefold() if CASE_INSENSITIVE_FS else real


def plan_hashes(root: Path) -> dict[str, str]:
    return {
        str(plan.relative_to(root)): hashlib.sha256(plan.read_bytes()).hexdigest()
        for plan in sorted(root.glob(".sdlc/*/plan.md"))
    }


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def emit(event: str, **fields: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, **fields}}, ensure_ascii=False))


def log_event(data: dict, kind: str, text: str) -> str:
    """Append one line to approvals.log and return it."""
    words = json.dumps(text.splitlines()[0][:80], ensure_ascii=False)
    cwd = json.dumps(str(data.get("cwd", "")), ensure_ascii=False)
    line = f"{now()} {kind} session={data.get('session_id')} cwd={cwd} prompt={words}"
    with (state_dir() / "approvals.log").open("a", encoding="utf-8") as log:
        log.write(line + "\n")
    return line


def start_run(data: dict, lock: Path, approved: Path) -> None:
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"since": now(), "cwd": data.get("cwd", "")}))
    approved.unlink(missing_ok=True)
    notes = [
        "sdlc-gate: code edits in this project are locked for this session until the owner "
        f"replies {UNLOCK_WORDS}. Files under .sdlc/ stay writable."
    ]
    rules = gate_home() / "rules" / "sdlc.md"
    if not rules.is_file():
        notes.append(f"sdlc-gate: {rules} is not installed, so the risk table this command uses is "
                     "missing. Tell the owner to run scripts/install.sh from the sdlc repo.")
    emit("UserPromptSubmit", additionalContext=" ".join(notes))


def approve(data: dict, lock: Path, approved: Path, text: str) -> None:
    plans = plan_hashes(project_root(data))
    if not plans:
        emit("UserPromptSubmit", additionalContext=(
            "sdlc-gate: no .sdlc/*/plan.md exists yet, so there is no plan to approve and code "
            "edits stay locked. Save plan.md, then ask the owner again."))
        return
    approved.write_text(json.dumps({"at": now(), "plans": plans}))
    lock.unlink(missing_ok=True)
    line = log_event(data, "approve", text)
    emit("UserPromptSubmit", additionalContext=(
        f"sdlc-gate: plan approval recorded: {line}. Bound to: {', '.join(plans)}. Copy this line "
        "into status.md. A change to any of these plan.md files locks code edits again."))


def release(data: dict, lock: Path, approved: Path, text: str) -> None:
    lock.unlink(missing_ok=True)
    approved.unlink(missing_ok=True)
    line = log_event(data, "release", text)
    emit("UserPromptSubmit", additionalContext=(
        f"sdlc-gate: released by the owner ({line}); code edits are no longer gated in this session."))


def on_prompt(data: dict) -> None:
    text = unicodedata.normalize("NFC", str(data.get("prompt", ""))).strip()
    lock, approved = session_file(data, "locked"), session_file(data, "approved")
    if lock is None or approved is None:
        return
    gated = lock.exists() or approved.exists()
    if RELEASE_PROMPT.fullmatch(text):
        if gated:
            release(data, lock, approved, text)
    elif SDLC_PROMPT.match(text):
        start_run(data, lock, approved)
    elif gated and APPROVE_PROMPT.fullmatch(text):
        approve(data, lock, approved, text)


def changed_plans(root: Path, approved: Path) -> list[str]:
    recorded = json.loads(approved.read_text()).get("plans", {})
    current = plan_hashes(root)
    return sorted(plan for plan in recorded.keys() | current.keys() if current.get(plan) != recorded.get(plan))


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
    except (OSError, ValueError):
        changed = ["an approved plan.md or the gate's record of it (unreadable)"]
    if changed:
        return (f"sdlc-gate: {', '.join(changed)} changed after the owner approved it, so code "
                f"edits are locked again. Show the owner what changed and ask them to reply {UNLOCK_WORDS}.")
    return ""


def file_edit_reason(data: dict, file_path: str) -> str:
    if not file_path:
        return ""
    target, root, state = canonical(file_path), canonical(project_root(data)), canonical(state_dir())
    if os.path.commonpath([target, state]) == state:
        return "sdlc-gate: the gate's state belongs to the owner; do not edit it."
    if os.path.commonpath([target, root]) != root:
        return ""
    first = Path(target).relative_to(root).parts[:1]
    return "" if first == (".sdlc",) else lock_reason(data, project_root(data))


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


def writes_files(command: str) -> bool:
    bare = re.sub(r"'[^']*'|\"[^\"]*\"", "''", command)
    bare = re.sub(r"(?<!\d)\d?>>?\s*/dev/null|(?<!\d)\d?>&\d", "", bare)
    return ">" in bare or bool(WRITE_COMMAND.search(bare))


def bash_reason(data: dict, command: str) -> str:
    agent = str(data.get("agent_type", "")).split(":")[-1]
    if agent in READ_ONLY_AGENTS and len(command) > MAX_CHECKED_COMMAND:
        return (f"sdlc-gate: {agent} is read-only, and this command is too long to check "
                f"({len(command)} characters). Split it into shorter read-only commands.")
    commit = commit_reason(command, str(data.get("cwd", "")))
    if commit:
        return commit
    if agent in READ_ONLY_AGENTS and writes_files(command):
        return (f"sdlc-gate: {agent} is read-only, and this command can change files or git state. "
                "Use read-only commands (git diff, git log, grep, the scanners).")
    return ""


def on_tool(data: dict) -> None:
    tool, tool_input = data.get("tool_name", ""), data.get("tool_input") or {}
    reason = ""
    if tool in FILE_TOOLS:
        reason = file_edit_reason(data, tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    elif tool == "Bash":
        reason = bash_reason(data, str(tool_input.get("command", "")))
    if reason:
        emit("PreToolUse", permissionDecision="deny", permissionDecisionReason=reason)


def trace(mode: str, data: dict) -> None:
    """With SDLC_GATE_TRACE set, record who called the hook, to check what the host sends."""
    fields = ("hook_event_name", "tool_name", "session_id", "agent_id", "agent_type")
    state_dir().mkdir(parents=True, exist_ok=True)
    with (state_dir() / "trace.log").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"mode": mode, **{key: data.get(key) for key in fields}}) + "\n")


def main() -> int:
    if os.environ.get("SDLC_GATE", "").lower() == "off":
        return 0
    os.umask(0o077)
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    data = json.load(sys.stdin)
    if os.environ.get("SDLC_GATE_TRACE"):
        trace(mode, data)
    if mode == "prompt":
        on_prompt(data)
    elif mode == "tool":
        on_tool(data)
    else:
        raise ValueError(f"sdlc_gate.py: unknown mode {mode!r}; expected 'prompt' or 'tool'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
