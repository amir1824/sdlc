#!/usr/bin/env python3
"""Count how many different tasks hit the same failure, from the retros of /sdlc runs. Reads only.

Usage: python3 -I scripts/failures.py [--min N] [--tags] [folder ...]

Looks for `.sdlc/<slug>/retro.md` under each folder (default: the current one; a symlinked folder
inside it is not followed) and reads the table under its `## Failures` heading: Tag, Stage,
Agent, Root cause, Evidence, Resolution. A `|` inside a cell is written `\\|`. Text in a code
fence is ignored. One task is one retro file, so a failure written twice in one retro counts
once, and the same slug in two projects counts twice. Output, most repeated first:

    3x  missing-call-sites  backend-developer
      app/task-a: review.md F2

A row with a tag outside the list (`--tags` prints it), without 6 cells, without an Agent or
Evidence, written as a quote or list item, and a retro that cannot be read (not a regular file,
over 1 MB, not UTF-8) are PROBLEM lines, and the exit code is 1; a folder argument that is not a
folder exits 2. A retro without the section (written before the table existed) is not a problem.
--min N hides failures seen in fewer than N tasks.
"""
import argparse
import os
import re
import stat
import sys
from collections import Counter
from pathlib import Path

# Keep in step with the tag list in plugins/sdlc/commands/sdlc.md (a test pins that they agree).
TAGS = ("missing-call-sites", "contract-mismatch", "unchecked-result", "missing-failure-path",
        "missing-instance", "unmet-criterion", "test-gap", "security-flaw", "env-assumption",
        "plan-miss", "other")
COLUMNS = 6
SKIP_DIRS = {".git", "node_modules"}
MAX_BYTES = 1_000_000
HEADING = re.compile(r"#{1,2}\s")
SECTION = re.compile(r"##\s+failures\b", re.IGNORECASE)
FENCES = ("```", "~~~")
QUOTED_ROW = re.compile(r"\s*(?:[>*+-]\s*)+\|")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
# ponytail: a full walk of each folder, no index. Point it at project folders, not at ~.


def find_retros(roots):
    """(real path, label) of each `.sdlc/<slug>/retro.md` once, however many folders reach it."""
    seen, found = set(), []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
            folder = Path(dirpath)
            if "retro.md" in filenames and folder.parent.name == ".sdlc":
                real = (folder / "retro.md").resolve()
                if real not in seen:
                    seen.add(real)
                    found.append((real, folder.resolve()))
    names = Counter(f"{task.parent.parent.name}/{task.name}" for _, task in found)
    return [(real, task_label(task, names)) for real, task in found]


def task_label(task, names):
    """`project/slug`, with the project's parent folder added when two tasks would look alike."""
    project = task.parent.parent
    short = f"{project.name}/{task.name}"
    return short if names[short] == 1 else f"{project.parent.name}/{short}"


def parse(text):
    """(has a Failures section, rows as 6-cell lists, problems) of one retro."""
    in_section = has_section = in_fence = False
    rows, problems = [], []
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if line.lstrip().startswith(FENCES):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if HEADING.match(line):
            in_section = bool(SECTION.match(line))
            has_section = has_section or in_section
            continue
        if not in_section:
            continue
        if QUOTED_ROW.match(line):
            problems.append(f"a table row must start with | at the start of the line, not in a quote or "
                            f"a list: {line.strip()}")
            continue
        body = line.strip()
        if not body.startswith("|"):
            continue
        body = body[1:]
        if body.endswith("|") and not body.endswith("\\|"):
            body = body[:-1]
        cells = [cell.replace("\\|", "|").strip().strip("`").strip() for cell in CELL_SPLIT.split(body)]
        joined = "".join(cells)
        if cells[0].lower() == "tag" or ("-" in joined and set(joined) <= set("-: ")):
            continue
        if len(cells) != COLUMNS:
            problems.append(f"a row needs {COLUMNS} cells: {line.strip()}")
        elif cells[0].lower() not in TAGS:
            problems.append(f"{cells[0]} is not in the tag list")
        elif not cells[2] or not cells[4]:
            problems.append(f"a row needs an Agent and Evidence: {line.strip()}")
        else:
            rows.append([cells[0].lower(), cells[1], cells[2].lower(), *cells[3:]])
    return has_section, rows, problems


def read_retro(path):
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("not a regular file")
    with path.open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("larger than 1 MB")
    return data.decode("utf-8-sig")


def collect(retros):
    """({(tag, agent): {(path, label): [evidence]}}, problems, retros with the section)."""
    groups, problems, with_section = {}, [], 0
    for path, label in retros:
        try:
            has_section, rows, row_problems = parse(read_retro(path))
        except (OSError, ValueError) as err:
            problems.append(f"{label}: {err}")
            continue
        with_section += 1 if has_section else 0
        problems.extend(f"{label}: {why}" for why in row_problems)
        for tag, _stage, agent, _cause, evidence, _resolution in rows:
            evidence_seen = groups.setdefault((tag, agent), {}).setdefault((path, label), [])
            if evidence not in evidence_seen:
                evidence_seen.append(evidence)
    return groups, problems, with_section


def render(groups, minimum):
    for (tag, agent), tasks in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(tasks) < minimum:
            continue
        print(f"{len(tasks)}x  {tag}  {agent}")
        for (_path, label), evidence in sorted(tasks.items(), key=lambda item: item[0][1]):
            print(f"  {label}: {' / '.join(evidence)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("folders", nargs="*", default=["."])
    parser.add_argument("--min", type=int, default=1, dest="minimum", help="hide failures seen in fewer tasks")
    parser.add_argument("--tags", action="store_true", help="print the tag list and stop")
    args = parser.parse_args()
    if args.tags:
        print("\n".join(TAGS))
        return
    for folder in args.folders:
        if not os.path.isdir(folder):
            print(f"failures: {folder} is not a folder", file=sys.stderr)
            sys.exit(2)

    retros = find_retros(args.folders)
    groups, problems, with_section = collect(retros)
    render(groups, args.minimum)
    for problem in problems:
        print(f"PROBLEM {problem}")
    print(f"retros: {len(retros)} read, {with_section} with a Failures table, {len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
