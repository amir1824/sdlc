#!/usr/bin/env python3
"""The security gate's verdict, computed from recorded Snyk scans with no model in the loop.

Usage:
  python3 -I security_gate.py     reads {"state": ..., "changed": [paths] or null, "tree": "<hash>"} on stdin and prints
                                  `Security gate: PASS|BLOCK|INCOMPLETE - <reasons>` then one line per finding.
                                  Exit 0 for a verdict, 2 when the input cannot be read.

`evaluate(state, facts)` is pure: it reads nothing and writes nothing. `facts` is what git said about the code: the
changed files, the hash of the code, and notes giving the reason for whatever git could not say. The state is the
project's record:
  policy    "on" (Snyk is required), "off" (the owner turned it off) or None (not decided)
  scans     {"code" | "sca" | "iac": {"status": "completed" | "error" | "unusable", "tree": <hash of the code
            that was scanned>, "findings": [{"id", "severity", "kind", "file", "flow": [files]}]}}
  accepted  finding ids the owner accepted in their own words
  waived    tree hashes for which the owner let an incomplete gate through
`changed` null means the change could not be listed (no base was pinned, or git failed): the gate is INCOMPLETE and
every finding counts as in the change. `tree` null means the code could not be hashed (too large, too slow, or git failed): every scan is `not hashed`.
INCOMPLETE is never PASS: a required scan that is missing, failed, narrowed or older than the code is
INCOMPLETE. A waiver changes whether the run may close, never the status.

ponytail: a finding counts as in the change when its file, or any step of its flow, is a changed file (a
dependency finding: a manifest or lockfile next to its own changed). That is conservative: it blocks on a
comment edit in a file with an old High. The upgrade is a scan of the base to compare finding ids.
ponytail: K8s and CloudFormation YAML need their content read to be told from other YAML, so only `.tf` and
`.tf.json` files require an IaC scan.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import PurePosixPath
from typing import NamedTuple

NOT_BLOCKING = frozenset({"low", "medium"})  # a severity not named here, however spelled, blocks
CODE_SUFFIXES = frozenset({
    ".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java", ".kt", ".go", ".rb", ".php", ".cs", ".vb",
    ".swift", ".m", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".scala", ".dart", ".ex", ".exs", ".groovy",
    ".cls", ".trigger", ".vue", ".svelte", ".html", ".htm"})
MANIFEST_NAMES = frozenset({
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "pipfile", "pipfile.lock", "poetry.lock",
    "pyproject.toml", "uv.lock", "go.mod", "go.sum", "cargo.toml", "cargo.lock", "pom.xml", "build.gradle",
    "build.gradle.kts", "gemfile", "gemfile.lock", "composer.json", "composer.lock", "packages.config"})
MANIFEST_PATTERN = re.compile(r"requirements[\w.-]*\.txt|.*\.csproj", re.IGNORECASE)
IAC_SUFFIXES = (".tf", ".tf.json")
RUN_FOLDER = ".sdlc"
KINDS = frozenset({"code", "sca", "iac"})
OWNER_WAIVER = "waived by owner for this code"
SHOWN_FINDINGS = 20
SHOWN_CHARS = 120


class Facts(NamedTuple):
    changed: list[str] | None
    tree: str | None
    notes: tuple[str, ...] = ()


POLICY_ON, POLICY_OFF, POLICY_UNREADABLE = "on", "off", "unreadable"


def clean_for_display(text: str) -> str:
    """Text from a scan reply, for the owner and the model: one line, no control or format characters, cut short."""
    return "".join(char if char.isprintable() else " " for char in text)[:SHOWN_CHARS]


def clean_path(path: str) -> str:
    return PurePosixPath(path).as_posix()


def scanner_for(path: str) -> str | None:
    name = PurePosixPath(path).name.lower()
    if name in MANIFEST_NAMES or MANIFEST_PATTERN.fullmatch(name):
        return "sca"
    if name.endswith(IAC_SUFFIXES):
        return "iac"
    return "code" if PurePosixPath(name).suffix in CODE_SUFFIXES else None


def required_scanners(changed: list[str]) -> frozenset[str]:
    """The scans a change needs, from its file names. The run's own folder is not part of the change."""
    paths = [clean_path(path) for path in changed if PurePosixPath(path).parts[:1] != (RUN_FOLDER,)]
    return frozenset(filter(None, map(scanner_for, paths)))


def finding_valid(item: object) -> bool:
    return (isinstance(item, dict) and item.get("kind") in KINDS
            and all(isinstance(item.get(key), str) for key in ("id", "severity", "file"))
            and isinstance(item.get("flow"), list) and all(isinstance(step, str) for step in item["flow"]))


def scan_problem(record: object, tree: str | None) -> str | None:
    """Why a scan record cannot back the gate: error, unusable (not a scan, narrowed, or not readable), or stale."""
    if not isinstance(record, dict):
        return "unusable"
    if record.get("status") == "error":
        return "error"
    findings = record.get("findings")
    if record.get("status") != "completed" or not isinstance(findings, list) or not all(map(finding_valid, findings)):
        return "unusable"
    if tree is None:
        return "not hashed"
    return "stale" if record.get("tree") != tree else None


def in_the_change(item: dict, changed: set[str] | None) -> bool:
    if changed is None:  # the change cannot be listed: every finding may be in it
        return True
    if item["kind"] == "sca":
        folder = PurePosixPath(item["file"]).parent
        return any(PurePosixPath(path).parent == folder and scanner_for(path) == "sca" for path in changed)
    return any(clean_path(path) in changed for path in (item["file"], *item["flow"]))


def describe(item: dict, changed: set[str] | None, accepted: set[str]) -> dict:
    blocking = item["severity"].lower() not in NOT_BLOCKING
    return {"id": item["id"], "severity": item["severity"].lower(), "kind": item["kind"], "file": item["file"],
            "class": "unknown" if in_the_change(item, changed) else "pre-existing", "blocking": blocking,
            "accepted": item["id"] in accepted}


def listed_findings(scans: dict, facts: Facts, accepted: set[str]) -> list[dict]:
    paths = None if facts.changed is None else {clean_path(path) for path in facts.changed}
    usable = [record for record in scans.values() if scan_problem(record, facts.tree) is None]
    found = [describe(item, paths, accepted) for record in usable for item in record["findings"]]
    ordered = sorted(found, key=lambda item: (item["file"], item["id"]))
    return [{**item, "short": f"F{number}"} for number, item in enumerate(ordered, 1)]


def strings(value: object) -> set[str]:
    return {item for item in value if isinstance(item, str)} if isinstance(value, list) else set()


def scan_reasons(required: frozenset[str], scans: dict, tree: str | None) -> list[str]:
    reasons = []
    for name in sorted(required):
        record = scans.get(name)
        problem = "not run" if record is None else scan_problem(record, tree)
        note = record.get("note") if isinstance(record, dict) else None
        if problem:
            reasons.append(f"{name}: {problem}" + (f" ({clean_for_display(note)})" if isinstance(note, str) else ""))
    return reasons


def evaluate(state: dict, facts: Facts) -> dict:
    policy = state.get("policy")
    if policy in (None, POLICY_OFF):
        reason = "Snyk: not decided" if policy is None else "Snyk off (the owner's choice)"
        return {"status": "PASS", "enforced": False, "closable": True, "reasons": [reason], "findings": []}
    if policy != POLICY_ON:
        return {"status": "INCOMPLETE", "enforced": True, "closable": False,
                "reasons": [f"policy `{policy}` is not on or off"], "findings": []}
    scans = state.get("scans") if isinstance(state.get("scans"), dict) else {}
    required = required_scanners(facts.changed or [])
    reasons = (["changed files: unknown"] if facts.changed is None else []) + list(facts.notes)
    reasons += scan_reasons(required, scans, facts.tree)
    listed = listed_findings(scans, facts, strings(state.get("accepted")))
    blockers = [item for item in listed if item["blocking"] and item["class"] == "unknown" and not item["accepted"]]
    reasons += [f"{item['short']} {item['severity']} {clean_for_display(item['file'])}: in the change, not accepted"
                for item in blockers[:SHOWN_FINDINGS]]
    if len(blockers) > SHOWN_FINDINGS:
        reasons.append(f"... and {len(blockers) - SHOWN_FINDINGS} more in the change, not accepted")
    status = "BLOCK" if blockers else "INCOMPLETE" if reasons else "PASS"
    if not required and facts.changed is not None:
        reasons.insert(0, "no scan required for this change")
    waived = status == "INCOMPLETE" and facts.tree in strings(state.get("waived"))
    return {"status": status, "enforced": True, "closable": status == "PASS" or waived,
            "reasons": reasons + ([OWNER_WAIVER] if waived else []), "findings": listed}


def report(result: dict) -> str:
    reasons = "; ".join(result["reasons"]) or "every required scan completed on this code"
    lines = [f"Security gate: {result['status']} - {reasons}"]
    shown = result["findings"][:SHOWN_FINDINGS]
    lines += [f"{item['short']} {clean_for_display(item['severity'])} {clean_for_display(item['file'])} {item['kind']} {item['class']}"
              f"{' (accepted)' if item['accepted'] else ''}" for item in shown]
    if len(result["findings"]) > SHOWN_FINDINGS:
        lines.append(f"... and {len(result['findings']) - SHOWN_FINDINGS} more findings")
    return "\n".join(lines)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        state, changed, tree = payload["state"], payload["changed"], payload["tree"]
        listed = changed is None or (isinstance(changed, list) and all(isinstance(p, str) for p in changed))
        if not (isinstance(state, dict) and (tree is None or isinstance(tree, str)) and listed):
            raise TypeError("wrong shape")
        result = evaluate(state, Facts(changed, tree))
    except (ValueError, KeyError, TypeError):
        print("Security gate: INCOMPLETE - input unreadable")
        return 2
    print(report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
