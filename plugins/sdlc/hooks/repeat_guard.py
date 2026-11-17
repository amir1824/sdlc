#!/usr/bin/env python3
"""Claude Code PostToolUse and PostToolUseFailure hook (Bash): tells the agent to stop when the same
test file keeps failing.

A failure is a PostToolUseFailure event, or a PostToolUse event of a test runner whose output shows a failed
run (a test command piped into `tail` exits 0, so the exit code alone misses it). The key is the test-file
path in the command, taken only from segments that run something: a `cat`, `grep` or `sed` of a test file
only reads it. Three failures of one key within 30 minutes, whatever passed in between, add a stop-and-report
note to the agent's context and a line to repeat.log in the gate's state folder.

Fails open: any error exits 0 with no output, so a broken hook never blocks work.
State is one small JSON file per session in SDLC_GATE_HOME (default ~/.claude)/sdlc-gate/; files a day old are
removed, each key keeps its last 10 failure times, and repeat.log stops growing at 100 kB.
REPEAT_GUARD_TRACE=<file> appends the event name and the payload's field names (never its content) there,
to check in a real session what the host sends. REPEAT_GUARD_NOW fixes the clock for tests.
ponytail: a loop that runs no test file with a path (a bare `npm test`) is not seen; the failure markers and
the runner words are heuristics; a run that a reading command starts (`git bisect run ...`) is ignored; a subagent stuck without running a command is not seen. Upgrade: count by
the failing test names in the output.
Standalone on purpose: `python3 -I` drops this folder from sys.path, and sdlc_gate.py is not imported.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

WINDOW_SECONDS = 30 * 60
THRESHOLD = 3
KEEP_TIMES = 10
STATE_MAX_AGE = 24 * 60 * 60
LOG_MAX_BYTES = 100_000
SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
TEST_PATH = re.compile(r"(?<![\w.-])(?:tests?|e2e)/[\w./-]+\.(?:py|ts|mjs)")
SEGMENT_END = re.compile(r"&&|\|\||[;|&\n()]")
FAILED_RUN = re.compile(r"\b[1-9]\d* failed\b|\bFAILED\b|Traceback \(most recent call last\)|AssertionError|✗|✖"
                        r"|^# fail [1-9]|^\s*(?:--- )?FAIL\b", re.MULTILINE)
RUNNER = re.compile(r"\b(?:pytest|vitest|jest|mocha|unittest|playwright|vite-node|tsx|ts-node|python3?|node|npx|npm|pnpm"
                    r"|yarn|bun|uv|bash|sh)\b|\bgo test\b|\bcargo test\b")
READERS = frozenset({"cat", "bat", "head", "tail", "less", "more", "grep", "egrep", "fgrep", "rg", "ag", "sed", "awk",
                     "git", "ls", "wc", "diff", "jq", "nl", "echo", "printf", "open", "code", "vim", "nano",
                     "stat", "file", "sort", "uniq", "cut", "tr", "tee"})
NOTE = ("repeat-guard: {key} failed {count} times in the last 30 minutes. Stop: write down what you tried and "
        "which hypotheses you ruled out, and report to the owner before another run.")


def state_dir() -> Path:
    return Path(os.environ.get("SDLC_GATE_HOME") or Path.home() / ".claude") / "sdlc-gate"


def output_text(response: object) -> str:
    if isinstance(response, dict):
        return "\n".join(str(response.get(name) or "") for name in ("stdout", "stderr"))
    return response if isinstance(response, str) else ""


def running_part(command: str) -> str:
    """The command without the segments that only read or print (a `sed` or `cat` of a test file)."""
    kept = []
    for segment in SEGMENT_END.split(command):
        words = [word for word in segment.split() if not re.match(r"\w+=", word)]
        if words and words[0].rsplit("/", 1)[-1] not in READERS:
            kept.append(segment)
    return " ; ".join(kept)


def is_failure(data: dict, running: str) -> bool:
    if data.get("hook_event_name") == "PostToolUseFailure":
        return True
    return bool(RUNNER.search(running)) and bool(FAILED_RUN.search(output_text(data.get("tool_response"))))


def load(path: Path) -> dict:
    try:
        loaded = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {key: times for key, times in loaded.items()
            if isinstance(times, list) and all(isinstance(t, (int, float)) for t in times)}


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(state))
    os.replace(temp, path)


def sweep(folder: Path, now: float) -> None:
    for pattern in ("*.repeat", "*.tmp"):
        for old in folder.glob(pattern):
            try:
                if now - old.stat().st_mtime > STATE_MAX_AGE:
                    old.unlink()
            except OSError:
                pass


def record(state: dict, key: str, now: float) -> int:
    live = {name: [t for t in times if now - t < WINDOW_SECONDS] for name, times in state.items()}
    live = {name: times for name, times in live.items() if times}
    live[key] = [*live.get(key, []), now][-KEEP_TIMES:]
    state.clear()
    state.update(live)
    return len(live[key])


def trace(data: dict) -> None:
    target = os.environ.get("REPEAT_GUARD_TRACE")
    if target:
        with open(target, "a") as handle:
            handle.write(f"{data.get('hook_event_name')} {data.get('tool_name')} {sorted(data)}\n")


def key_for(data: dict, running: str) -> str | None:
    paths = sorted(set(TEST_PATH.findall(running)))
    session = str(data.get("session_id") or "")
    if not paths or not SESSION_ID.fullmatch(session):
        return None
    agent = re.sub(r"[^\w-]", "_", str(data.get("agent_id") or "main"))[:64]
    return f"{agent}|{','.join(paths)}"


def log_note(session: str, now: float, count: int, shown: str) -> None:
    log = state_dir() / "repeat.log"
    if log.exists() and log.stat().st_size > LOG_MAX_BYTES:
        return
    with open(log, "a") as handle:
        handle.write(f"{int(now)} {session} {count} {shown}\n")


def handle(data: dict) -> None:
    trace(data)
    command = (data.get("tool_input") or {}).get("command")
    if data.get("tool_name") != "Bash" or not isinstance(command, str):
        return
    running = running_part(command)
    key = key_for(data, running) if is_failure(data, running) else None
    if key is None:
        return
    path = state_dir() / f"{data['session_id']}.repeat"
    state = load(path)
    now = float(os.environ.get("REPEAT_GUARD_NOW") or time.time())
    count = record(state, key, now)
    save(path, state)
    sweep(path.parent, now)
    if count >= THRESHOLD:
        shown = key.split("|", 1)[1]
        log_note(data["session_id"], now, count, shown)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": data.get("hook_event_name"),
                                                 "additionalContext": NOTE.format(key=shown, count=count)}},
                         ensure_ascii=False))


def main() -> None:
    os.umask(0o077)
    try:
        handle(json.load(sys.stdin))
    except Exception:  # fail open: a broken hook must not stop the owner's work
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
