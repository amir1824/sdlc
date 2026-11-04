#!/usr/bin/env python3
"""Check that the lessons library and the installed agents agree. Reads only; writes nothing.

Usage: python3 -I scripts/check_lessons.py [--lessons <path>] [--agents <dir>]

A lesson whose status is `promoted (<agents>, "<text>", <date>)` was written into those agent
files. For each agent installed in <dir>, the quoted text must be in the file:
  ok        the text is there
  DRIFT     the text is missing (a local copy of the agent was never given the promotion)
  missing   the agent is not installed (normal when the plugin is installed instead; not a problem)
  UNCHECKED the status line names no agent or no quoted text, or an agent name that is not a plain
            file name; the line cannot be checked, so the owner fixes it
  stale     a rating recorded another hash of the agent file than the one installed now (the file
            changed since it was rated; not a problem; `rate_lesson.py --agent` records the hash)
Exit code: 0 with no DRIFT or UNCHECKED line, 1 with one, 2 when the lessons file cannot be read.
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

AGENT_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
PROMOTED = "- status: promoted"


def fingerprint(path):
    # rate_lesson.py computes the same hash; change both together (a test pins that they agree).
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def sections(text):
    """(lesson id, its lines) for each `## <id> ...` section."""
    found, current = [], None
    for line in text.split("\n"):
        head = re.match(r"## (\S+)", line)
        if head:
            current = (head.group(1), [])
            found.append(current)
        elif current:
            current[1].append(line)
    return found


def field(lines, name):
    return next((line for line in lines if line.startswith(f"- {name}:")), "")


def promotion(status):
    """(agent names, quoted text) of a promoted status line, or None when it cannot be read."""
    rest = status[len(PROMOTED):]
    if not (rest == "" or rest[0] in " ("):
        return None
    body = rest[rest.find("(") + 1:rest.rfind(")")] if "(" in rest and ")" in rest else ""
    quoted = re.search(r'"([^"]+)"', body)
    if not quoted or not quoted.group(1).strip():
        return None
    names = [n for n in re.split(r"\s*(?:,|\band\b)\s*", body[:quoted.start()].strip()) if n]
    if not names or not all(AGENT_NAME.fullmatch(n) for n in names):
        return None
    return names, quoted.group(1).strip()


def report(tag, message):
    print(f"{tag:<8} {message}")


def check_agent(lesson_id, lines, name, quoted, agents_dir):
    """Report one promoted lesson against one installed agent; True when it is a problem."""
    path = agents_dir / f"{name}.md"
    if not path.is_file():
        report("missing", f"{lesson_id} {name}")
        return False
    try:
        body = path.read_text(encoding="utf-8")
        now = fingerprint(path)
    except (OSError, ValueError) as err:
        report("UNCHECKED", f"{lesson_id} {name}: {err}")
        return True
    problem = quoted not in body
    if problem:
        report("DRIFT", f'{lesson_id} {name}: "{quoted}" is not in {path}')
    else:
        report("ok", f"{lesson_id} {name}")
    rated = re.findall(rf"(?<![\w-]){re.escape(name)}@([0-9a-f]{{10}})", field(lines, "used"))
    if rated and rated[-1] != now:
        report("stale", f"{lesson_id} {name}: rated at {rated[-1]}, the file is now {now}")
    return problem


def check(text, agents_dir):
    problems = promoted = 0
    for lesson_id, lines in sections(text):
        status = field(lines, "status")
        if not status.startswith(PROMOTED):
            continue
        promoted += 1
        parsed = promotion(status)
        if parsed is None:
            report("UNCHECKED", f'{lesson_id}: the status line needs the agents and a quoted text: '
                                'promoted (<agents>, "<text>", <date>)')
            problems += 1
            continue
        names, quoted = parsed
        problems += sum(check_agent(lesson_id, lines, name, quoted, agents_dir) for name in names)
    return promoted, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--lessons", type=Path, default=Path.home() / ".claude/lessons/LESSONS.md")
    parser.add_argument("--agents", type=Path, default=Path.home() / ".claude/agents")
    args = parser.parse_args()
    try:
        text = args.lessons.read_text(encoding="utf-8")
    except (OSError, ValueError) as err:
        print(f"check_lessons: {err}", file=sys.stderr)
        sys.exit(2)
    promoted, problems = check(text, args.agents)
    print(f"lessons: {promoted} promoted, {problems} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
