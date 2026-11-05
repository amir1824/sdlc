#!/usr/bin/env python3
"""Rate a lessons-library entry from an A/B eval, and write the rating to LESSONS.md.

Usage: python3 -I scripts/rate_lesson.py <result.json> <lesson id> [--agent <file> ...]
                                         [--regression <before.json>] [--lessons <path>]

<result.json> is what `claude plugin eval --json <file>` wrote for a run of the lesson's case
pair, `lesson-<id>-with` and `lesson-<id>-without`: the same prompt and graders, with the
lesson in the builder's plan and without it. Each run passed or did not; the gap between the
two pass rates is the verdict. It is added to the lesson's `used` line; `hurt` retires the
lesson, whatever its status, and `helped` raises its confidence to medium. No rating makes a
`proposed` lesson `library`: that is the owner's yes.

--agent <file> (repeatable) adds the file's name and a short hash to the entry, so a later
reader can tell which version of the agent was rated; `scripts/check_lessons.py` compares it
with the installed file.

--regression <before.json> checks a promotion instead of rating a pair: <result.json> is an
eval of all of the edited agent's cases, <before.json> the same cases before the edit. A case
both files hold, with at least 3 runs and no error or skipped paid grader in each, is judged; it dropped when its pass
rate fell by half or more. A case <before.json> holds and <result.json> lacks makes the verdict
`confounded`. The verdict (`ok`, `REGRESSED` or `confounded`) goes to the `used` line, under a key
of the start time and the --agent names (two agents' records in one minute do not replace each
other), and nothing else in the lesson changes. The exit code is 0 only for `ok`.

The script ships in the sdlc repo, not in the plugin: run it from a clone.
"""
import argparse
import hashlib
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
AGENT_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")  # the same rule check_lessons.py applies
PLAIN_TEXT = re.compile(r"[^;\x00-\x1f\x7f]*")  # what may enter a `used` entry: no `; ` separator, no line break


def fail(message):
    print(f"rate_lesson: {message}; LESSONS.md not changed", file=sys.stderr)
    sys.exit(2)


def arm_runs(result, case_name):
    """The runs of one case with the plugin loaded (`--ablation none` gives no other arm)."""
    for case in result.get("cases", []):
        if case.get("name") == case_name:
            return case.get("arms", {}).get("with", [])
    fail(f"no case named {case_name} in the result")


def is_clean(runs):
    return not any(run.get("error") or run.get("skippedPaidGraders") for run in runs)


def pass_count(runs):
    return sum(1 for run in runs if run.get("passed"))


def verdict(with_runs, without_runs, partial):
    with_pass = pass_count(with_runs)
    without_pass = pass_count(without_runs)
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


def regression_verdict(before, after):
    """Compare the cases both results hold; a case that fell by half or more in pass rate dropped."""
    old_cases = {case.get("name"): case.get("arms", {}).get("with", []) for case in before.get("cases", [])}
    judged, unjudged, dropped = 0, 0, []
    for case in after.get("cases", []):
        old, new = old_cases.get(case.get("name")), case.get("arms", {}).get("with", [])
        if old is None:
            continue
        if min(len(old), len(new)) < MIN_RUNS or not (is_clean(old) and is_clean(new)):
            unjudged += 1
            continue
        judged += 1
        if Fraction(pass_count(new), len(new)) - Fraction(pass_count(old), len(old)) <= -GAP:
            dropped.append(f"{case.get('name')} {pass_count(old)}/{len(old)} -> {pass_count(new)}/{len(new)}")
    if dropped:
        return "REGRESSED", ", ".join(dropped)
    if judged == 0:
        return "confounded", "no case judged"
    missing = sorted(name for name in old_cases if name not in {case.get("name") for case in after.get("cases", [])})
    if missing:
        return "confounded", f"{judged} judged, but the result lacks {', '.join(missing)}"
    skipped = f", {unjudged} unjudged" if unjudged else ""
    if before.get("partial") or after.get("partial"):
        return "confounded", f"the eval stopped early, {judged} judged{skipped}, none dropped"
    return "ok", f"{judged} judged{skipped}, none dropped"


def fingerprint(path):
    # check_lessons.py computes the same hash; change both together (a test pins that they agree).
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def agents_note(paths):
    if not paths:
        return ""
    for path in paths:
        if not AGENT_NAME.fullmatch(path.stem):
            fail(f"the agent name '{path.stem}' has characters the used line cannot hold")
    try:
        return ", agents " + " ".join(f"{path.stem}@{fingerprint(path)}" for path in paths)
    except OSError as err:
        fail(str(err))


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


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        fail(str(err))


def check_shape(result, label):
    """Stop on an eval result the script cannot read, before anything is written (exit 2, never 1)."""
    def bad(why):
        fail(f"{label} is not an eval result: {why}")

    if not isinstance(result, dict):
        bad("not a JSON object")
    started = result.get("startedAt", "unknown")
    if not isinstance(started, str) or not PLAIN_TEXT.fullmatch(started):
        bad("startedAt is not plain text")
    cases = result.get("cases", [])
    if not isinstance(cases, list):
        bad("cases is not a list")
    for case in cases:
        name = case.get("name") if isinstance(case, dict) else None
        if not isinstance(name, str) or not PLAIN_TEXT.fullmatch(name):
            bad("a case has no plain-text name")
        arms = case.get("arms", {})
        runs = arms.get("with", []) if isinstance(arms, dict) else None
        if not isinstance(runs, list) or not all(isinstance(run, dict) for run in runs):
            bad(f"case {name} has malformed runs")


def write_atomically(target, lines):
    target = target.resolve()
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".LESSONS.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write("\n".join(lines))
    os.chmod(tmp, stat.S_IMODE(target.stat().st_mode))
    os.replace(tmp, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("result", type=Path)
    parser.add_argument("lesson", help="the lesson's ID, e.g. L1")
    parser.add_argument("--lessons", type=Path, default=Path.home() / ".claude/lessons/LESSONS.md")
    parser.add_argument("--agent", type=Path, action="append", default=[],
                        help="an agent file whose name and hash go into the entry")
    parser.add_argument("--regression", type=Path, metavar="BEFORE",
                        help="the eval result from before the agent edit; check the edit for regressions")
    args = parser.parse_args()

    result = read_json(args.result)
    before = read_json(args.regression) if args.regression else None
    check_shape(result, "the result")
    if before is not None:
        check_shape(before, "the baseline")
    try:
        text = args.lessons.read_text(encoding="utf-8")
    except (OSError, ValueError) as err:
        fail(str(err))
    lesson_id = args.lesson.upper()
    agents = list(dict.fromkeys(args.agent))
    note = agents_note(agents)
    started = result.get("startedAt", "unknown")[:16]

    if before is None:
        pair = f"lesson-{lesson_id.lower()}"
        rating, detail = verdict(arm_runs(result, f"{pair}-with"), arm_runs(result, f"{pair}-without"),
                                 bool(result.get("partial")))
        key = f"eval {pair} {started}"
    else:
        rating, detail = regression_verdict(before, result)
        key = " ".join(["regression", started, *(path.stem for path in agents)])

    lines = text.split("\n")
    start, end = section_bounds(lines, lesson_id)
    used = field_index(lines, start, end, "used")
    changed = {used: add_used_entry(lines[used], key, f"{key}: {rating} ({detail}{note})")}
    was_promoted = False
    if before is None and rating == "hurt":
        status = field_index(lines, start, end, "status")
        was_promoted = lines[status].startswith("- status: promoted")
        changed[status] = "- status: retired"
    if before is None and rating == "helped":
        confidence = field_index(lines, start, end, "confidence")
        if lines[confidence].rstrip() == "- confidence: low":
            changed[confidence] = "- confidence: medium"
    for i, line in changed.items():
        lines[i] = line

    write_atomically(args.lessons, lines)
    print(f"{lesson_id}: {rating} ({detail})")
    for i in sorted(changed):
        print(f"  {lines[i]}")
    if was_promoted:
        print(f"  {lesson_id} was promoted: revert its text in the agent or skill it was written into.")
    if rating == "REGRESSED":
        print(f"  {lesson_id}: the agent edit made a case worse: revert it, or fix it and run both evals again.")
    if before is not None and rating != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
