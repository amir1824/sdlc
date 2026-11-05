#!/usr/bin/env python3
"""Freeze a set of eval cases, check that they stayed frozen, and keep a baseline per agent version.

Usage:
  python3 -I scripts/suite.py freeze   <manifest.json> <evals dir> <case> [<case> ...]
  python3 -I scripts/suite.py check    <manifest.json> <evals dir> [--baselines <dir> --agents-dir <dir>]
  python3 -I scripts/suite.py baseline <result.json> [<result.json> ...] --agent-file <file> --out <dir>
                                       [--runs 5] [--manifest <manifest.json>] [--config <path> ...]

freeze records the sha256 of every file under each named case folder (prompt, case.yaml,
scaffold, graders); a symlink or a file that is not a plain file inside a case is refused. It
never overwrites a manifest: a frozen suite changes by a new manifest.
check exits 1 when a case folder differs from its hash (CHANGED) or is gone (MISSING). With
--baselines it also says `stale`, and exits 1, when no baseline was taken for the agent file as it is now,
or when a file under the baseline's `--config` paths changed, vanished or appeared since it was taken.
baseline turns `claude plugin eval --json` results into `<out>/<agent>-<hash>.json`: the agent is
the agent file's name without `.md`, and the hash is the first 10 hex characters of the file's
sha256 (the one `rate_lesson.py --agent` records). It keeps the pass, error, cost and time of each run of the agent's cases
(`<agent>-*`; an agent whose name is the start of another's, `qa` and `qa-engineer`, would take its
cases, and no such pair exists), in the shape `rate_lesson.py --regression` reads. A later result replaces the
runs of a case it holds, so a case that timed out is rerun alone. A case with an errored run,
a skipped paid grader or fewer than --runs runs is listed as RERUN (exit 1): the regression
check would leave it unjudged; with --manifest, so is each frozen case of the agent that the results
do not hold. --runs below 3 is refused (the regression check judges no case with fewer). A partial
result is refused. A file that cannot be read or written exits 2, never 1.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

CASE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
AGENT_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
PLAIN_TEXT = re.compile(r"[^;\x00-\x1f\x7f]*")
BASELINE_FILE = re.compile(r"(?P<agent>[a-z0-9][a-z0-9-]*)-(?P<hash>[0-9a-f]{10})\.json")
IGNORED_FILES = {".DS_Store"}
IGNORED_DIRS = {"__pycache__", ".git", "node_modules"}
MIN_RUNS = 3  # what rate_lesson.py --regression needs in a case to judge it


def fail(message):
    print(f"suite: {message}", file=sys.stderr)
    sys.exit(2)


def report(tag, message):
    print(f"{tag:<8} {message}")


def fingerprint(path):
    # rate_lesson.py and check_lessons.py compute the same hash; change all three together.
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def case_hash(folder):
    digest = hashlib.sha256()
    files = []
    for dirpath, dirnames, filenames in os.walk(folder):
        for name in dirnames:
            if os.path.islink(os.path.join(dirpath, name)):
                raise ValueError(f"{os.path.join(dirpath, name)} is a symlink; a frozen case holds plain files")
        files.extend(Path(dirpath, name) for name in filenames if name not in IGNORED_FILES)
    for path in sorted(files):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{path} is not a plain file; a frozen case holds plain files")
        digest.update(path.relative_to(folder).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def config_snapshot(roots):
    """{path: short hash} of every file under the given files and folders: what the agent runs with besides
    its own file (the /sdlc command, rules, hooks, skills). Paths are kept as given, not resolved, so a
    symlink pointed at another folder shows as changed files; symlinks are followed to hash the target.
    Only regular files count (a pipe would block the read)."""
    snapshot = {}
    for given in roots:
        root = Path(os.path.abspath(given))
        if root.is_file():
            files = [root]
        elif root.is_dir():
            files = []
            for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
                dirnames[:] = [name for name in dirnames if name not in IGNORED_DIRS]
                files.extend(Path(dirpath, name) for name in filenames if name not in IGNORED_FILES)
        else:
            raise ValueError(f"{given} is not a file or a folder")
        snapshot.update({str(path): fingerprint(path) for path in files if path.is_file()})
    return snapshot


def config_drift(baseline_file):
    """What differs between the config a baseline was taken with and the config now ('' when nothing)."""
    config = read_json(baseline_file).get("config")
    if not isinstance(config, dict):
        return ""
    try:
        now = config_snapshot(config.get("roots", []))
    except ValueError as err:
        return f"config root gone: {err}"
    then = config.get("files", {})
    changes = [f"{path} changed" for path in sorted(then) if path in now and now[path] != then[path]]
    changes += [f"{path} gone" for path in sorted(then) if path not in now]
    changes += [f"{path} added" for path in sorted(now) if path not in then]
    return "config " + "; ".join(changes) if changes else ""


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        fail(f"{path}: {err}")


def read_manifest(path):
    data = read_json(path)
    cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(cases, dict) or not all(
            isinstance(name, str) and CASE_NAME.fullmatch(name) and isinstance(digest, str)
            for name, digest in cases.items()):
        fail(f"{path} is not a manifest: it needs a \"cases\" object of case name to hash")
    return cases


def freeze(args):
    manifest = Path(args.manifest)
    cases = {}
    for name in args.cases:
        folder = Path(args.evals) / name
        if not CASE_NAME.fullmatch(name) or not folder.is_dir():
            fail(f"{name} is not a case folder under {args.evals}")
        cases[name] = case_hash(folder)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(manifest, "x", encoding="utf-8") as out:
            out.write(json.dumps({"cases": cases}, indent=2) + "\n")
    except FileExistsError:
        fail(f"{manifest} exists; a frozen suite changes by a new manifest, not by overwriting this one")
    print(f"froze {len(cases)} cases in {manifest}")


def stale_baselines(baselines, agents_dir):
    """Report each agent whose baseline is for an older file; return how many."""
    stale = 0
    hashes = {}
    for path in sorted(Path(baselines).glob("*.json")):
        match = BASELINE_FILE.fullmatch(path.name)
        if match:
            hashes.setdefault(match["agent"], set()).add(match["hash"])
    for agent, taken in sorted(hashes.items()):
        agent_file = Path(agents_dir) / f"{agent}.md"
        if not agent_file.is_file():
            report("missing", f"{agent}: no agent file in {agents_dir}")
        elif fingerprint(agent_file) not in taken:
            report("stale", f"{agent}: no baseline for the file now ({fingerprint(agent_file)})")
            stale += 1
        elif drift := config_drift(Path(baselines) / f"{agent}-{fingerprint(agent_file)}.json"):
            report("stale", f"{agent}: {drift}")
            stale += 1
    return stale


def check(args):
    cases = read_manifest(args.manifest)
    problems = 0
    for name, frozen in sorted(cases.items()):
        folder = Path(args.evals) / name
        if not folder.is_dir():
            report("MISSING", name)
            problems += 1
        elif case_hash(folder) != frozen:
            report("CHANGED", f"{name}: the files differ from the frozen hash")
            problems += 1
        else:
            report("ok", name)
    if args.baselines:
        problems += stale_baselines(args.baselines, args.agents_dir)
    print(f"suite: {len(cases)} cases, {problems} problem(s)")
    sys.exit(1 if problems else 0)


def slim_run(run):
    error = run.get("error")
    return {"passed": bool(run.get("passed")), "error": str(error)[:80] if error else None,
            "skippedPaidGraders": bool(run.get("skippedPaidGraders")),
            "costUsd": run.get("costUsd"), "durationSeconds": run.get("durationSeconds")}


def agent_runs(result, agent, label):
    """({case name: slim runs} for the cases of one agent, startedAt, claude version) of one eval result."""
    if not isinstance(result, dict) or not isinstance(result.get("cases", []), list):
        fail(f"{label} is not an eval result")
    if result.get("partial"):
        fail(f"{label} is partial: the eval stopped early; run it again")
    started = result.get("startedAt", "unknown")
    if not isinstance(started, str) or not PLAIN_TEXT.fullmatch(started):
        fail(f"{label}: startedAt is not plain text")
    runs = {}
    for case in result.get("cases", []):
        name = case.get("name") if isinstance(case, dict) else None
        if not isinstance(name, str):
            fail(f"{label} has a case without a name")
        if not name.startswith(f"{agent}-"):
            continue
        arms = case.get("arms")
        raw = arms.get("with") if isinstance(arms, dict) else None
        if not CASE_NAME.fullmatch(name) or not isinstance(raw, list) or not all(isinstance(run, dict) for run in raw):
            fail(f"{label}: the case {name} cannot be read")
        runs[name] = [slim_run(run) for run in raw]
    return runs, started, result.get("claudeVersion")


def rerun_reasons(runs, needed):
    reasons = []
    if len(runs) < needed:
        reasons.append(f"{len(runs)} runs, {needed} needed")
    if any(run["error"] for run in runs):
        reasons.append(f"{sum(1 for run in runs if run['error'])} errored")
    if any(run["skippedPaidGraders"] for run in runs):
        reasons.append("a paid grader was skipped")
    return reasons


def baseline(args):
    agent_file = Path(args.agent_file)
    agent = agent_file.stem
    if not AGENT_NAME.fullmatch(agent) or agent_file.suffix != ".md":
        fail(f"{agent_file.name} is not an agent file (<name>.md with a lower-case, dashed name)")
    if args.runs < MIN_RUNS:
        fail(f"--runs {args.runs} is below {MIN_RUNS}: the regression check judges no case with fewer")
    agent_hash = fingerprint(agent_file)
    merged = {}
    for path in args.results:
        runs, file_started, file_version = agent_runs(read_json(path), agent, path)
        if runs:  # a file without the agent's cases says nothing about when its runs were taken
            started, version = file_started, file_version
        merged.update(runs)
    if not merged:
        fail(f"no case named {agent}-* in the results")
    target = Path(args.out) / f"{agent}-{agent_hash}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    cases = [{"name": name, "arms": {"with": merged[name]}} for name in sorted(merged)]
    data = {"agent": agent, "agentHash": agent_hash, "startedAt": started, "claudeVersion": version,
            "partial": False, "cases": cases}
    if args.config:
        data["config"] = {"roots": [os.path.abspath(root) for root in args.config],
                          "files": config_snapshot(args.config)}
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    reruns = 0
    for case in cases:
        runs = case["arms"]["with"]
        reasons = rerun_reasons(runs, args.runs)
        if reasons:
            reruns += 1
            report("RERUN", f"{case['name']}: {'; '.join(reasons)}")
        else:
            cost = sum(run["costUsd"] or 0 for run in runs)
            report("ok", f"{case['name']}: {len(runs)} runs, {sum(run['passed'] for run in runs)} passed, ${cost:.2f}")
    if args.manifest:
        for name in sorted(read_manifest(args.manifest)):
            if name.startswith(f"{agent}-") and name not in merged:
                reruns += 1
                report("RERUN", f"{name}: not in the results")
    sys.exit(1 if reruns else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    freeze_parser = commands.add_parser("freeze")
    freeze_parser.add_argument("manifest")
    freeze_parser.add_argument("evals")
    freeze_parser.add_argument("cases", nargs="+")
    freeze_parser.set_defaults(run=freeze)
    check_parser = commands.add_parser("check")
    check_parser.add_argument("manifest")
    check_parser.add_argument("evals")
    check_parser.add_argument("--baselines")
    check_parser.add_argument("--agents-dir", default=str(Path.home() / ".claude/agents"))
    check_parser.set_defaults(run=check)
    baseline_parser = commands.add_parser("baseline")
    baseline_parser.add_argument("results", nargs="+")
    baseline_parser.add_argument("--agent-file", required=True)
    baseline_parser.add_argument("--manifest", help="a frozen suite: its cases of the agent must all be in the results")
    baseline_parser.add_argument("--config", action="append", default=[], metavar="PATH",
                                 help="a file or folder the agent runs with (commands, rules, hooks, skills); repeatable")
    baseline_parser.add_argument("--out", required=True)
    baseline_parser.add_argument("--runs", type=int, default=5)
    baseline_parser.set_defaults(run=baseline)
    args = parser.parse_args()
    try:
        args.run(args)
    except (OSError, ValueError) as err:
        fail(str(err))


if __name__ == "__main__":
    main()
