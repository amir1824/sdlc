"""The owner's `sdlc snyk on|off|accept|waive` words, for sdlc_hooks/snyk_gate.py: only typed words reach UserPromptSubmit, so
these are the owner's. `host` is the SnykHost snyk_gate.py builds; an error before the record is written leaves it
as it was, and the approvals log is written after it.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

LOG_MAX = 200
REASON_MAX = 500
BASE_SHOWN = 12


class OwnerCommand(NamedTuple):
    data: dict
    root: Path
    state: dict


def say_on_off_words_refused(host, verb: str) -> None:
    host.say(f"`sdlc snyk {verb}` takes no other words; type it alone. Nothing was changed.")


def run(host, data: dict, text: str) -> None:
    parsed = host.load("snyk/close").parse_command(text)
    if parsed is None:
        return host.say("`sdlc snyk` takes on, off, accept F<number> <reason>, or waive <reason>.")
    verb, words = parsed
    root, gate = host.root(data), host.load("security_gate")
    context = OwnerCommand(data, root, host.read_state(root))
    if verb in (gate.POLICY_ON, gate.POLICY_OFF):
        return say_on_off_words_refused(host, verb) if words else set_policy(host, context, verb)
    if context.state["policy"] == gate.POLICY_UNREADABLE:
        return host.say("the Snyk record of this project cannot be read: type `sdlc snyk on` or `sdlc snyk off` first.")
    return accept_finding(host, context, words) if verb == "accept" else waive_gate(host, context, words)


def append_owner_log(state: dict, entry: dict) -> None:
    state["log"] = [*(state["log"] if isinstance(state["log"], list) else []), entry][-LOG_MAX:]


def unique_strings(value: object) -> list[str]:
    return list(dict.fromkeys(item for item in value if isinstance(item, str))) if isinstance(value, list) else []


def policy_note(is_off: bool, base: str | None) -> str:
    if is_off:
        return "Snyk is no longer required in this project: a run may close with no scan."
    pinned = (f"Changes are measured from {base[:BASE_SHOWN]}." if base else
              "No base commit could be pinned (is this a git repo with a commit?), so the gate stays INCOMPLETE.")
    return ("Snyk is required in this project. Snyk Code uploads the project's source to Snyk's servers, and typing "
            f"this is the owner's consent to that. A run closes, or Ship starts, only when the Security gate is PASS. {pinned}")


def set_policy(host, context: OwnerCommand, verb: str) -> None:
    """`on` pins the base commit when Snyk was not already on (typing it again mid-run must not move the base)."""
    gate = host.load("security_gate")
    state, was = context.state, context.state["policy"]
    state["policy"] = verb
    if verb == gate.POLICY_ON and (was != gate.POLICY_ON or not state.get("base")):
        state["base"] = host.load("snyk/record").head_or_none(host, context.root) or state.get("base")
    append_owner_log(state, {"at": host.now(), "verb": verb, "reason": ""})
    host.write_state(context.root, state)
    host.log_event(context.data, f"snyk-{verb}", f"sdlc snyk {verb}")
    host.say(policy_note(verb == gate.POLICY_OFF, state.get("base")))


def accept_finding(host, context: OwnerCommand, words: str) -> None:
    gate, guard = host.load("security_gate"), host.load("snyk/guard")
    args = host.load("snyk/close").accept_args(words)
    if args is None:
        return host.say("`sdlc snyk accept F<number> <reason>` needs a finding and a reason in the owner's words.")
    budget = host.load("snyk/tree").new_budget()
    listed = guard.verdict(host, guard.Scope(context.root, context.state), budget)
    found = [item for item in listed["findings"] if item["short"] == args[0]]
    if not found:
        return host.say(f"{args[0]} is not a finding of the current scans.\n{gate.report(listed)}")
    state, reason = context.state, args[1][:REASON_MAX]
    state["accepted"] = unique_strings([*unique_strings(state["accepted"]), found[0]["key"]])
    append_owner_log(state, {"at": host.now(), "verb": "accept", "reason": reason, "finding": found[0]["id"]})
    host.write_state(context.root, state)
    host.log_event(context.data, "snyk-accept", f"{args[0]} {reason}")
    host.say(f"accepted {args[0]} ({gate.clean_for_display(found[0]['file'])}): {args[1]}.\n"
             + gate.report(guard.verdict(host, guard.Scope(context.root, state), budget)))


def waive_gate(host, context: OwnerCommand, words: str) -> None:
    tree, guard = host.load("snyk/tree"), host.load("snyk/guard")
    budget = tree.new_budget()
    try:
        code = tree.tree_hash(context.root, budget)
    except tree.TreeUnavailable as error:
        return host.say(f"`sdlc snyk waive <reason>` needs a project whose code git can hash: {error}.")
    if not words:
        return host.say("`sdlc snyk waive <reason>` needs a reason in the owner's words.")
    state, reason = context.state, words[:REASON_MAX]
    state["waived"] = unique_strings([*unique_strings(state["waived"]), code])
    append_owner_log(state, {"at": host.now(), "verb": "waive", "reason": reason, "tree": code})
    host.write_state(context.root, state)
    host.log_event(context.data, "snyk-waive", reason)
    result = guard.verdict(host, guard.Scope(context.root, state), budget)
    host.say(f"the incomplete Snyk gate is waived for the code as it is now: {words}. A change to the code, or a "
             "finding, is not covered.\n" + host.load("security_gate").report(result))
