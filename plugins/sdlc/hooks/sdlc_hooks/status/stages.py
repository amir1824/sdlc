"""Checks of a run's status.md that look past its stage lines, for status_check.py: that a stage starts only when the
one before it is done or skipped, that a HIGH run whose Verify is done has a test run in review.md, and that the
`intake:` header key, when there is one, names a result. They read only, and what they return is advice: nothing here
blocks a write.
"""
from __future__ import annotations

import re
from pathlib import Path

COMPLETE = ("done", "skipped")
STARTED = ("running", "done")
AMENDED_PLAN_REASON = "plan amended"  # the reason commands/sdlc.md has the run write on a blocked Build
BUILD, VERIFY = 5, 6
FILE_MAX_BYTES = 1024 * 1024
QUOTE_CHARS = 80
STAGES = ("Discover", "Define", "Design", "Plan", "Build", "Verify", "Ship", "Launch", "Learn")
TEST_RUNS_HEADING = re.compile(r"\s*(?:#+\s*|\*\*)Test runs")
TABLE_HEAD_LINES = 2  # the header row and its separator
INTAKE_RESULTS = ("READY", "NEEDS_INFO", "RESCOPE_PROPOSED", "REJECTED")


def is_blocked_by_plan_amendment(state: str, reason: str) -> bool:
    """A stage the owner's plan amendment sent back (the caller says it is Build): its later stages still say done from before."""
    return state == "blocked" and AMENDED_PLAN_REASON in reason


def order_findings(stages: dict[int, tuple[str, str]]) -> list[str]:
    """A running or done stage whose nearest earlier stage is neither done nor skipped; a done stage after a Build
    blocked by an amended plan is the update in progress, not a finding."""
    found = []
    for number, (state, _) in sorted(stages.items()):
        behind = next((earlier for earlier in range(number - 1, 0, -1)
                       if earlier in stages and stages[earlier][0] not in COMPLETE), None) if state in STARTED else None
        if behind is None:
            continue
        behind_state, behind_reason = stages[behind]
        if not (state == "done" and behind == BUILD and is_blocked_by_plan_amendment(behind_state, behind_reason)):
            found.append(f"stage {number} {STAGES[number - 1]} is {state} but stage {behind} {STAGES[behind - 1]} "
                         f"is {behind_state}")
    return found


def test_run_rows(review: str) -> int:
    """How many rows the table under `Test runs` holds (its header row and separator not counted)."""
    lines = review.splitlines()
    start = next((index for index, line in enumerate(lines) if TEST_RUNS_HEADING.match(line)), None)
    if start is None:
        return 0
    section = []
    for line in lines[start + 1:]:
        if line.startswith("#"):
            break
        section.append(line)
    table = [line for line in section if line.lstrip().startswith("|")]
    return max(len(table) - TABLE_HEAD_LINES, 0)


def test_run_findings(folder: Path, header: dict[str, str], stages: dict[int, tuple[str, str]]) -> list[str]:
    """A HIGH run whose Verify is done must show at least one test run; a missing review.md is reported elsewhere."""
    review = folder / "review.md"
    if header.get("risk") != "HIGH" or stages.get(VERIFY, ("", ""))[0] != "done":
        return []
    if review.is_symlink() or not review.is_file() or review.stat().st_size > FILE_MAX_BYTES:
        return []
    if test_run_rows(review.read_text(encoding="utf-8", errors="replace")):
        return []
    return ["stage 6 Verify is done but review.md has no row under Test runs (HIGH risk)"]


def intake_findings(header: dict[str, str]) -> list[str]:
    """An `intake:` key is optional (a run with none is READY); when it is there it is one of the four results."""
    result = header.get("intake", INTAKE_RESULTS[0])
    if result in INTAKE_RESULTS:
        return []
    return [f"header: intake `{result[:QUOTE_CHARS]}` is not {', '.join(INTAKE_RESULTS[:-1])} or {INTAKE_RESULTS[-1]}"]
