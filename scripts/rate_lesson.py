#!/usr/bin/env python3
"""Rate a lessons-library entry from an A/B eval, and write the rating to LESSONS.md.

Usage: python3 -I scripts/rate_lesson.py <result.json> <lesson id> [--lessons <path>]

<result.json> is what `claude plugin eval --json <file>` wrote for a run of the lesson's case
pair, `lesson-<id>-with` and `lesson-<id>-without`: the same prompt and graders, with the
lesson in the builder's plan and without it. Each run passed or did not; the gap between the
two pass rates is the verdict. It is added to the lesson's `used` line; `hurt` retires the
lesson, whatever its status, and `helped` raises its confidence to medium. No rating makes a
`proposed` lesson `library`: that is the owner's yes.

The script ships in the sdlc repo, not in the plugin: run it from a clone.
"""
import argparse
import json
import os
import re
import stat
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

MIN_RUNS = 3
GAP = Fraction(1, 2)
# ponytail: a fixed pass-rate gap on 3 to 5 runs per arm, no significance test (3/3 against 0/3
# is p=0.1, Fisher two-sided). Past about 10 runs per arm, use Fisher's exact test instead.


def fail(message):
    print(f"rate_lesson: {message}; LESSONS.md not changed", file=sys.stderr)
    sys.exit(2)


def arm_runs(result, case_name):
    """The runs of one case with the plugin loaded (`--ablation none` gives no other arm)."""
    for case in result.get("cases", []):
        if case.get("name") == case_name:
            return case.get("arms", {}).get("with", [])
    fail(f"no case named {case_name} in the result")


def verdict(with_runs, without_runs, partial):
    with_pass = sum(1 for run in with_runs if run.get("passed"))
    without_pass = sum(1 for run in without_runs if run.get("passed"))
    counts = f"with {with_pass}/{len(with_runs)}, without {without_pass}/{len(without_runs)}"
    if any(run.get("error") for run in with_runs + without_runs):
        return "confounded", f"{counts}, a run errored"
    if any(run.get("skippedPaidGraders") for run in with_runs + without_runs):
        return "confounded", f"{counts}, a run skipped its paid graders"
    if partial:
        return "confounded", f"{counts}, the eval stopped early"
    if min(len(with_runs), len(without_runs)) < MIN_RUNS:
        return "confounded", f"{counts}, fewer than {MIN_RUNS} runs in an arm"
    gap = Fraction(with_pass, len(with_runs)) - Fraction(without_pass, len(without_runs))
    if gap >= GAP:
        return "helped", counts
    if gap <= -GAP:
        return "hurt", counts
    return "no observed effect", counts


def section_bounds(lines, lesson_id):
    head = re.compile(rf"^## {re.escape(lesson_id)}(\s|$)")
    start = next((i for i, line in enumerate(lines) if head.match(line)), None)
    if start is None:
        fail(f"no section '## {lesson_id}' in the lessons file")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return start, end


def field_index(lines, start, end, field):
    for i in range(start, end):
        if lines[i].startswith(f"- {field}:"):
            return i
    fail(f"the lesson has no '- {field}:' line")


def add_used_entry(line, key, entry):
    current = line.split(":", 1)[1].strip()
    entries = [] if current == "none yet" else [e for e in current.split("; ") if e]
    entries = [e for e in entries if not e.startswith(f"{key}:")] + [entry]
    return "- used: " + "; ".join(entries)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("result", type=Path)
    parser.add_argument("lesson", help="the lesson's ID, e.g. L1")
    parser.add_argument("--lessons", type=Path, default=Path.home() / ".claude/lessons/LESSONS.md")
    args = parser.parse_args()

    try:
        result = json.loads(args.result.read_text(encoding="utf-8"))
        text = args.lessons.read_text(encoding="utf-8")
    except (OSError, ValueError) as err:
        fail(str(err))
    lesson_id = args.lesson.upper()
    pair = f"lesson-{lesson_id.lower()}"
    rating, detail = verdict(arm_runs(result, f"{pair}-with"), arm_runs(result, f"{pair}-without"),
                             bool(result.get("partial")))

    lines = text.split("\n")
    start, end = section_bounds(lines, lesson_id)
    used = field_index(lines, start, end, "used")
    key = f"eval {pair} {result.get('startedAt', 'unknown')[:16]}"
    changed = {used: add_used_entry(lines[used], key, f"{key}: {rating} ({detail})")}
    was_promoted = False
    if rating == "hurt":
        status = field_index(lines, start, end, "status")
        was_promoted = lines[status].startswith("- status: promoted")
        changed[status] = "- status: retired"
    if rating == "helped":
        confidence = field_index(lines, start, end, "confidence")
        if lines[confidence].rstrip() == "- confidence: low":
            changed[confidence] = "- confidence: medium"
    for i, line in changed.items():
        lines[i] = line

    target = args.lessons.resolve()
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".LESSONS.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write("\n".join(lines))
    os.chmod(tmp, stat.S_IMODE(target.stat().st_mode))
    os.replace(tmp, target)
    print(f"{lesson_id}: {rating} ({detail})")
    for i in sorted(changed):
        print(f"  {lines[i]}")
    if was_promoted:
        print(f"  {lesson_id} was promoted: revert its text in the agent or skill it was written into.")


if __name__ == "__main__":
    main()
