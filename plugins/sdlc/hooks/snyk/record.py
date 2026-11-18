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


def scan_verdict(host, root: Path, state: dict, code: str | None, budget) -> str:
    """The Security gate's line for the code as it is now, worked out on the budget the scan's hash already drew on
    (a second budget would double the hook's time). "" when Snyk is not required in this project; `waiting - <scans still
    to run>` while that is the only thing missing."""
    gate, tree = host.load("security_gate"), host.load("snyk/tree")
    if state["policy"] != gate.POLICY_ON:
        return ""
    try:
        changed, notes = tree.changed_files(root, state.get("base"), budget), ()
    except tree.TreeUnavailable as error:
        changed, notes = None, (f"changed files: {error}",)
    result = gate.evaluate(state, gate.Facts(changed, code, notes))
    if result.get("waiting"):  # the other scans are still to come: that is no verdict yet, but the chair is told which
        return "Security gate: waiting - " + "; ".join(result["reasons"])
    return gate.report(result)


def record_scan(host, data: dict) -> str:
    """PostToolUse and PostToolUseFailure: record a Snyk scan of this project in the project's state, and return the
    gate's verdict line for the owner and the model ("" when there is none to say). A scan whose code cannot be
    hashed is recorded as unusable, with the reason, since it cannot be told from later code. The scan is written
    before the verdict is worked out, so a verdict that fails or runs out of time never loses it."""
    events, tree = host.load("snyk/events"), host.load("snyk/tree")
    if str(data.get("tool_name", "")).rsplit("__", 1)[-1] not in events.SCAN_TOOLS:
        return ""
    project, root, budget = host.project(data), host.root(data), tree.new_budget()
    try:
        code, note = tree.tree_hash(root, budget), None
    except tree.TreeUnavailable as error:
        code, note = None, str(error)
    found = events.record_from_event(data, project, code)
    if found is None:
        return ""
    scanner, record = found
    if note and record["status"] == "unusable":
        record = {**record, "note": note}
    state = host.read_state(root)
    state = {**state, "scans": {**state["scans"], scanner: record}}
    host.write_state(root, state)
    try:
        return scan_verdict(host, root, state, code, budget)
    except Exception:  # noqa: BLE001 - advisory: the scan is recorded, and the close gate says the verdict again
        return ""


def reset_accepted(host, root: Path) -> int:
    """At a plan approval: what the owner accepted ends with the plan it was accepted under. Returns how many were
    cleared and writes nothing when there were none (an unreadable record has none to clear)."""
    state = host.read_state(root)
    accepted = state.get("accepted")
    cleared = len(accepted) if isinstance(accepted, list) else 0
    if cleared:
        log = {"at": host.now(), "verb": "accept-reset", "reason": f"{cleared} cleared at a plan approval"}
        host.load("snyk/owner").append_owner_log(state, log)
        host.write_state(root, {**state, "accepted": []})
    return cleared


def pin_base(host, root: Path) -> None:
    """At a plan approval: record HEAD as the commit the change is measured from, when none is pinned. No base leaves
    the gate incomplete, which is the safe side."""
    state = host.read_state(root)
    head = None if state.get("base") else head_or_none(host, root)
    if head:
        host.write_state(root, {**state, "base": head})
