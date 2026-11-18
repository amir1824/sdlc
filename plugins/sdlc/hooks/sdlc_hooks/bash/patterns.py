"""The regular expressions of the Bash checks. Every pattern is linear: a separator or a newline ends any repeat, so a
hostile command cannot run the hook past its timeout (which fails open).
"""
from __future__ import annotations

import re

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

LEADING_FLAGS = r"(?:-" + WORD + r"+" + SPACE + r")*"
INLINE_CODE_END = r"(?=[\s'\";&|)=]|$)"
PREFIX = (r"(?:(?:sudo|time|nohup|command|exec|then|do|else)" + SPACE + r")*(?:env" + SPACE + r")?"
          + r"(?:\w+=" + WORD + r"*" + SPACE + r")*(?:(?:uv|poetry|pipenv)" + SPACE + r"run" + SPACE + r")?")

# ponytail: a denylist of the common ways to write, not a sandbox. A quoted verb, a script file that
# writes, a verb built at run time, a command substitution inside a commit message, a heredoc fed to
# `ssh` or `xargs`, and any verb not listed get through; an OS sandbox is the upgrade.
WRITE_COMMAND = re.compile(
    COMMAND_START + PREFIX
    + r"(?:xargs" + SPACE + r"(?:-" + WORD + r"+" + SPACE + r")*)?\\?" + BINARY_PATH
    + r"(?:rm|rmdir|mv|cp|tee|touch|mkdir|chmod|chown|ln|truncate|dd|eval)" + VERB_END
    + r"|" + COMMAND_START + BINARY_PATH + r"(?:ba|z)?sh" + SPACE + r"(?:-" + WORD + r"+" + SPACE + r")*-c"
    + VERB_END
    + r"|" + COMMAND_START + BINARY_PATH + r"sed" + SPACE + r"(?:" + WORD + r"+" + SPACE + r")*?(?:-i|--in-place)"
    + r"|" + COMMAND_START + BINARY_PATH + r"perl" + SPACE + r"(?:" + WORD + r"+" + SPACE + r")*?-\w*i"
    + r"|" + COMMAND_START + PREFIX + BINARY_PATH + r"(?:python[\d.]*" + SPACE + LEADING_FLAGS + r"-\w*c"
    + r"|(?:node|nodejs|ruby|perl|bun)" + SPACE + LEADING_FLAGS + r"(?:-\w*[eE]|--eval|-p)"
    + r"|php" + SPACE + LEADING_FLAGS + r"-r|deno" + SPACE + r"eval)" + INLINE_CODE_END
    + r"|" + COMMAND_START + PREFIX + BINARY_PATH
    + r"(?:python[\d.]*|node|nodejs|ruby|perl|php|bun|(?:ba|z|da|k)?sh|fish|source|\.)(?:[ \t]+[^\s<;&|]+)*[ \t]*<<"
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

# awk hides its program in quotes, which writes_files strips, so these two are read on the raw command.
AWK_START = re.compile(COMMAND_START + PREFIX + BINARY_PATH + r"[gmn]?awk" + VERB_END)
AWK_WRITE = re.compile(r"\bprintf?\b[^}\n]{0,200}>>?(?!=)|\bsystem[ \t]*\(|-i[ \t]+inplace\b")

# Only a plain path counts as scratch: a quote, `$`, `\` or `..` in the target fails the match, so the
# redirect is judged a write. ponytail: a symlink under /tmp is not followed.
SCRATCH_REDIRECT = re.compile(r"(?<!\d)\d?>>?[ \t]*/(?:private/)?tmp/(?![\w./+-]*\.\.)[\w./+-]*(?=[\s;&|)]|$)")
COMMIT_MESSAGE = re.compile(r"(?<=[ \t])(?:-[a-zA-Z]*m|--message)(?:=|[ \t]*)(?:'[^']*'|\"[^\"]*\"|[^\s;&|'\"]+)")

GIT_COMMIT = re.compile(COMMAND_START + r"(?:\w+=" + WORD + r"*" + SPACE + r")*" + GIT + r"commit\b")
COMMIT_STATEMENT = re.compile(r"(?P<head>" + GIT_COMMIT.pattern + r")(?P<args>(?:[^;&|\n'\"]|'[^']*'|\"[^\"]*\")*)")
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
