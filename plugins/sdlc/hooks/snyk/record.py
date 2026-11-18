"""Recording a Snyk scan and pinning the base commit, for sdlc_hooks/snyk_gate.py. `host` is the SnykHost it builds."""
from __future__ import annotations

from pathlib import Path


def head_or_none(host, root: Path) -> str | None:
    """HEAD, or None when the project has no repo or no commit (the caller keeps the base it had, or none)."""
    tree = host.load("snyk/tree")
    try:
        return tree.head_commit(root)
    except tree.TreeUnavailable:
        return None


def record_scan(host, data: dict) -> None:
    """PostToolUse and PostToolUseFailure: record a Snyk scan of this project in the project's state. A scan whose code
    cannot be hashed is recorded as unusable, with the reason, since it cannot be told from later code."""
    events, tree = host.load("snyk/events"), host.load("snyk/tree")
    if str(data.get("tool_name", "")).rsplit("__", 1)[-1] not in events.SCAN_TOOLS:
        return
    project, root = host.project(data), host.root(data)
    try:
        code, note = tree.tree_hash(root), None
    except tree.TreeUnavailable as error:
        code, note = None, str(error)
    found = events.record_from_event(data, project, code)
    if found is None:
        return
    scanner, record = found
    if note and record["status"] == "unusable":
        record = {**record, "note": note}
    state = host.read_state(root)
    host.write_state(root, {**state, "scans": {**state["scans"], scanner: record}})


def pin_base(host, root: Path) -> None:
    """At a plan approval: record HEAD as the commit the change is measured from, when none is pinned. No base leaves
    the gate incomplete, which is the safe side."""
    state = host.read_state(root)
    head = None if state.get("base") else head_or_none(host, root)
    if head:
        host.write_state(root, {**state, "base": head})
