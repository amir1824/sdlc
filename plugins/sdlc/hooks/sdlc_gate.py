#!/usr/bin/env python3
"""The sdlc gate hooks for Claude Code: one script, two hook events.

`prompt` (UserPromptSubmit): a typed `/sdlc` locks code edits in that session; a reply of
exactly `approve plan` or `אשר תוכנית` unlocks them and binds the approval to the hash of
each `.sdlc/*/plan.md`; with more than one plan.md the reply names the plan, `approve plan
<folder>`. When that plan holds an `sdlc-scope` block, its patterns are frozen into the approval
and only matching files may be edited. A reply of exactly `sdlc off` releases the session.
`tool` (PreToolUse): denies an edit in the project while the session is locked or after an
approved plan.md changed or a new one appeared, an edit outside the frozen scope, a `fix:`
commit without an `Evidence:` line (a message it cannot read is judged on the command text),
and a Bash command that writes from a read-only review agent.

Fails open: any error exits non-zero (never 2), so Claude Code lets the action through. Two
exceptions deny instead, because an error there would lift a limit that is on: the scope check, and
a file path the gate cannot read while a run is locked or approved. SDLC_GATE=off disables the
gate; SDLC_GATE_SCOPE=off only the scope.
SDLC_GATE_HOME (default ~/.claude) holds sdlc-gate/ and rules/.
ponytail: the gate stops a misread reply, not an agent set on getting past it. Bash writes
(scope included) are not gated, Bash can delete the gate's state, and a run resumed in
a new session needs the approval typed again; an OS sandbox and a lock keyed by run lift these.
Edits outside CLAUDE_PROJECT_DIR (a sibling package of a larger repo) are never gated.
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
APPROVE_PROMPT = re.compile(
    r"(?:approve plan|אשר תוכנית)(?:[ \t]+(?P<slug>[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9_-])?))?[\s.!]*",
    re.IGNORECASE)
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
UNLOCK_WORDS = ("exactly `approve plan` (or `אשר תוכנית`; with more than one plan.md, add the plan's folder "
                "name after it), or `sdlc off` to leave the pipeline")
SCOPE_FENCE = "```sdlc-scope"
SCOPE_MAX_ENTRIES, SCOPE_MAX_ENTRY, SCOPE_MAX_BYTES, SCOPE_MAX_PARTS = 100, 200, 8192, 100
SCOPE_TAG = "sdlc-gate: [scope] "
FENCE_MARKS = ("```", "~~~")
PATH_KEYS = ("file_path", "notebook_path")
# An approved scope never covers these, wherever they sit in the tree: they hold the hooks, the
# settings and the tool config that bind the agent.
PROTECTED_NAMES = (".git", ".claude", ".mcp.json")
# Patterns that match almost all of these are no limit.
# ponytail: a sample test, not a count against the real tree. A list of four or more plain file
# extensions is refused as "nearly every file", and a union of narrow folder patterns (b*/**,
# c*/** ...) can slip under it; the owner reads the frozen list in the approval notice. The upgrade
# is to count matches against `git ls-files` at approval.
BROAD_SAMPLES = ("a/b.txt", "src/x.py", "docs/y.md", "x", "deep/er/path/file.tsx")


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


def emit(event: str, system_message: str = "", **fields: str) -> None:
    """The hook's reply: `fields` go to the model; `system_message`, when given, is for the owner."""
    out: dict = {"hookSpecificOutput": {"hookEventName": event, **fields}}
    if system_message:
        out["systemMessage"] = system_message
    print(json.dumps(out, ensure_ascii=False))


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


def opens_scope_fence(line: str) -> bool:
    return "sdlc-scope" in line and line.lstrip().startswith(FENCE_MARKS)


def parse_scope(text: str) -> list[str] | None:
    """The patterns of the plan's one `sdlc-scope` block; None when it has none; ValueError when it
    is malformed or when what the gate would freeze could differ from what the owner reads, so
    approval is refused while a person is watching, not at edit time."""
    lines = text.split("\n")
    if any(opens_scope_fence(line) and line.rstrip() != SCOPE_FENCE for line in lines):
        raise ValueError("a line opens a code fence for `sdlc-scope` but is not the exact fence: three "
                         "backticks at the start of the line, then `sdlc-scope`")
    starts = [n for n, line in enumerate(lines) if line.rstrip() == SCOPE_FENCE]
    if not starts:
        return None
    if len(starts) > 1:
        raise ValueError("it holds more than one `sdlc-scope` block")
    # ponytail: counting fence lines, so an unclosed inner fence can fool it; a second block is
    # still refused and the owner reads the frozen list, so it can mis-signal but not widen.
    if sum(line.lstrip().startswith(FENCE_MARKS) for line in lines[:starts[0]]) % 2:
        raise ValueError("its `sdlc-scope` block sits inside another code fence")
    body = []
    for line in lines[starts[0] + 1:]:
        if line.rstrip() == "```":
            break
        body.append(line)
    else:
        raise ValueError("its `sdlc-scope` block is not closed with ```")
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


def has_scope_block(text: str) -> bool:
    """Whether the plan holds a scope block or a fence that looks like one (parse_scope refuses it)."""
    return any(opens_scope_fence(line) for line in text.split("\n"))


def choose_plan(root: Path, plans: dict[str, str], slug: str | None) -> tuple[str | None, str]:
    """(the plan to approve, "") or (None, why not). With several plan.md files and no scope block in
    any, the choice decides nothing and no name is needed: (None, ""). Once one holds a block the owner
    names the plan, because the choice decides which paths may be edited."""
    names = sorted(plans)
    if slug:
        target = f".sdlc/{slug}/plan.md"
        return (target, "") if target in plans else (None, f"no plan named `{slug}`; the plans are {', '.join(names)}.")
    if len(names) == 1:
        return names[0], ""
    if any(has_scope_block((root / name).read_text(encoding="utf-8", errors="replace")) for name in names):
        return None, (f"more than one plan.md exists ({', '.join(names)}) and one holds a scope block. The owner "
                      "replies `approve plan <folder>` with the folder name under .sdlc/ of the plan they approve.")
    return None, ""


def refuse(why: str) -> None:
    emit("UserPromptSubmit", system_message=f"sdlc-gate: {why}",
         additionalContext=f"sdlc-gate: {why} Code edits stay locked.")


def approve(data: dict, lock: Path, approved: Path, text: str, slug: str | None = None) -> None:
    root = project_root(data)
    plans = plan_hashes(root)
    if not plans:
        emit("UserPromptSubmit", additionalContext=(
            "sdlc-gate: no .sdlc/*/plan.md exists yet, so there is no plan to approve and code "
            "edits stay locked. Save plan.md, then ask the owner again."))
        return
    target, globs = None, None
    try:
        target, why = choose_plan(root, plans, slug)
        if why:
            return refuse(why)
        if target:
            raw = (root / target).read_bytes()
            globs = parse_scope(raw.decode("utf-8", errors="replace"))
            plans[target] = hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError) as exc:
        return refuse(f"{target or 'a plan.md'} cannot be approved: {exc}. Fix the plan, then ask the owner again.")
    record = {"at": now(), "plans": plans}
    if globs is not None:
        record["scope"] = {"plan": target, "globs": globs}
    line = log_event(data, "approve", text)  # logged before the approval takes effect: a log error leaves the lock on
    log_event(data, "scope", f"{target or 'all plans'} scope={'none' if globs is None else len(globs)}")
    approved.write_text(json.dumps(record))
    lock.unlink(missing_ok=True)
    limit = ("No `sdlc-scope` block was approved, so edits are not limited to a set of paths." if globs is None
             else f"Edits are limited to {len(globs)} pattern(s) from {target}: {', '.join(globs)}.")
    emit("UserPromptSubmit", system_message=f"sdlc-gate: plan approved. {limit}", additionalContext=(
        f"sdlc-gate: plan approval recorded: {line}. Bound to: {', '.join(plans)}. {limit} Copy this line "
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
    elif gated:
        approval = APPROVE_PROMPT.fullmatch(text)
        if approval:
            approve(data, lock, approved, text, approval.group("slug"))


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
    except Exception:  # any damage to the record counts as unreadable, and locks
        changed = ["an approved plan.md or the gate's record of it (unreadable)"]
    if changed:
        return (f"sdlc-gate: {', '.join(changed)} changed after the owner approved it, so code "
                f"edits are locked again. Show the owner what changed and ask them to reply {UNLOCK_WORDS}.")
    return ""


def approved_scope(data: dict) -> list[str] | None:
    """The patterns frozen into this session's approval; None when it is not path-limited."""
    approved = session_file(data, "approved")
    if os.environ.get("SDLC_GATE_SCOPE", "").lower() == "off" or approved is None or not approved.exists():
        return None
    scope = json.loads(approved.read_text()).get("scope")
    if scope is None:
        return None
    globs = scope["globs"]
    if not isinstance(globs, list) or not globs or not all(isinstance(glob, str) for glob in globs):
        raise ValueError("the scope in the gate's record is not a list of patterns")
    return globs


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


def protected(relative: str) -> bool:
    return any(part in PROTECTED_NAMES for part in relative.split("/"))


def written_inside_project(data: dict, file_path: str) -> bool:
    """Whether the path, as written and before symlinks are followed, lies in the project, by either
    spelling of its root."""
    base = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
    written = os.path.abspath(file_path)
    return any(os.path.commonpath([written, root]) == root for root in (os.path.abspath(base), os.path.realpath(base)))


def file_edit_reason(data: dict, file_path: str) -> str:
    if not file_path:
        return ""
    file_path = os.path.join(str(data.get("cwd") or ""), file_path)
    target, root, state = canonical(file_path), canonical(project_root(data)), canonical(state_dir())
    if os.path.commonpath([target, state]) == state:
        return "sdlc-gate: the gate's state belongs to the owner; do not edit it."
    if os.path.commonpath([target, root]) != root:
        return scope_reason(data, None) if written_inside_project(data, file_path) else ""
    relative = Path(target).relative_to(root)
    if relative.parts[:1] == (".sdlc",):
        return ""
    return lock_reason(data, project_root(data)) or scope_reason(data, relative.as_posix())


def session_gated(data: dict) -> bool:
    return any(path is not None and path.exists() for path in (session_file(data, "locked"), session_file(data, "approved")))


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


def note_scope_denial(data: dict, path: str) -> None:
    """Log a scope denial after it was emitted, so a failed write cannot drop the denial."""
    try:
        log_event(data, "deny-scope", path)
    except Exception:  # best effort: the denial is already printed
        pass


def on_tool(data: dict) -> None:
    tool, tool_input = data.get("tool_name", ""), data.get("tool_input") or {}
    reason, path = "", "?"
    if tool in FILE_TOOLS:
        reason, path = file_tool_reason(data, tool_input)
    elif tool == "Bash":
        reason = bash_reason(data, str(tool_input.get("command", "")))
    if reason:
        emit("PreToolUse", permissionDecision="deny", permissionDecisionReason=reason)
        if reason.startswith(SCOPE_TAG):
            note_scope_denial(data, str(path))


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
