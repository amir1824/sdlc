"""The `mcp` and `jira-seen` modes: no MCP write in a session with a Jira run.

`mcp` (PreToolUse, matcher `^mcp__`): in a session with a Jira run, denies every MCP tool whose name does not
start with a read verb (so a ticket cannot make the chair write to Atlassian, or send its text out through
another server), except the host app's own bookkeeping tools (APP_TOOLS). A session has a Jira run when the owner
typed `/sdlc jira KEY` or `/sdlc resume jira-key` (`jira` followed by ordinary words is an ordinary request; a
token that looks like a key or a link but was not understood still counts), when the prompt that starts a run, or
a gated session's reply, holds an atlassian.net/browse link, or when a gated session finds `.sdlc/jira-*` in the
project; the marker is the file `sdlc-gate/<session>.jira` (only its existence is read), which only `sdlc off`
removes. A Jira run also writes `sdlc-gate/<session>.jira-intake` (it holds the key, or `?` when none was
understood): `approve plan` is refused while it exists, and `jira-seen` (PostToolUse, matcher on the ticket reads)
removes it when this session reads that ticket and the `labels` (or `fields.labels`) list of the response, a JSON
object, holds the label (SDLC_JIRA_LABEL, default `sdlc`). Free text is never searched, so a ticket cannot spell
its own label; a response in another shape leaves the intake pending, and the owner can reply `sdlc intake off`
to go on without the label check: only the intake goes, the write block and the code lock stay.
ponytail: this stops a slip by the chair or text in a ticket, not a shell: Bash can delete the markers, as it can
the lock; a `claude -p` child has its own session; `curl` and `acli` are not MCP; a crash or a timeout of the hook
allows; a new `session_id` (/clear, a resume) has no marker, as it has no lock; an old `.sdlc/jira-*` folder marks
a later gated session on its first MCP write; a name is judged by its words, so a write named like a read gets
through when none of its words is in WRITE_WORDS; and the label is the owner's intent, not who set it; a tool with a read name but attacker-chosen arguments
(fetch a URL, search) can still carry data out.
"""
from __future__ import annotations

import json
import re

from sdlc_hooks.core import deny, emit, log_event, session_file
from sdlc_hooks.jira.markers import NO_KEY, gated_session_with_jira_run, intake_pending, jira_label, jira_marker_exists, mark_jira, words_of
from sdlc_hooks.snyk_gate import snyk_scan_allowed

EXECUTE_READ = re.compile(r"execute[_-]?read", re.IGNORECASE)  # a wrapper: the operation it names must read too

MAX_RESPONSE_CHARS = 1_000_000

# The host app's own task-list and chapter tools: not a way out of the session, and the chair needs them.
APP_TOOLS = frozenset({"mcp__ccd_turn__update_plan", "mcp__ccd_turn__wrap_up", "mcp__ccd_session__mark_chapter"})

READ_WORDS = frozenset({"get", "search", "list", "lookup", "fetch", "find", "query", "view", "describe",
                        "discover", "read"})
WRITE_WORDS = frozenset({"create", "update", "edit", "delete", "add", "remove", "transition", "assign", "write",
                         "publish", "upload", "replace", "merge", "archive", "import", "clone", "rank", "send",
                         "close", "reopen", "destructive", "set", "run", "execute", "post", "push", "put", "patch",
                         "move", "submit", "trigger", "apply", "save", "insert", "drop", "reset", "share", "invite",
                         "grant", "revoke", "notify", "email", "mail", "reply", "approve", "cancel", "start", "stop",
                         "copy", "sync", "deploy", "forward", "invoke", "and", "then"})
READ_NAMES = frozenset({"atlassianuserinfo", "atlassianhome"})


def reads_only(name: str, tool_input: dict) -> bool:
    if EXECUTE_READ.fullmatch(name):
        return reads_only(str(tool_input.get("name", "")), {})
    words = words_of(name)
    if words[:1] in (["jira"], ["confluence"]):
        words = words[1:]
    return name.lower() in READ_NAMES or bool(words and words[0] in READ_WORDS and WRITE_WORDS.isdisjoint(words))


def mcp_reason(data: dict) -> str:
    """Why this MCP call may not run, or "". Only a tool that does not read is judged, and only in a session
    with a Jira run: a read costs the hook no file read."""
    tool, tool_input = str(data.get("tool_name", "")), data.get("tool_input") or {}
    parts = tool.split("__", 2)
    name = parts[2] if len(parts) == 3 and parts[0] == "mcp" else ""
    if not name or tool in APP_TOOLS or reads_only(name, tool_input):
        return ""
    if not (jira_marker_exists(data) or gated_session_with_jira_run(data)):
        return ""
    if snyk_scan_allowed(data, (parts[1], name, tool_input)):
        return ""
    return (f"sdlc-gate: {name} is an MCP tool that may change something outside this session, and this "
            "session has a Jira run, which only reads. If it is wanted, the owner replies `sdlc off`.")


def reads_issue(data: dict) -> bool:
    """Whether this tool call reads one Jira issue: getJiraIssue, or executeRead naming it."""
    tool, tool_input = str(data.get("tool_name", "")), data.get("tool_input") or {}
    parts = tool.split("__", 2)
    name = parts[2] if len(parts) == 3 and parts[0] == "mcp" else ""
    if EXECUTE_READ.fullmatch(name):
        name = str(tool_input.get("name", ""))
    return "".join(words_of(name)) in ("getjiraissue", "jiragetissue")


def issue_objects(response: object) -> list[dict]:
    """The JSON objects a tool response carries: the response itself, or the text of its content blocks."""
    blocks = response if isinstance(response, list) else [response]
    if isinstance(response, dict) and isinstance(response.get("content"), list):
        blocks = [response] + response["content"]
    found = [block for block in blocks if isinstance(block, dict)]
    for block in blocks:
        text = block if isinstance(block, str) else block.get("text") if isinstance(block, dict) else None
        if isinstance(text, str) and text.lstrip()[:1] == "{":
            try:
                parsed = json.loads(text[:MAX_RESPONSE_CHARS])
            except (ValueError, RecursionError):
                continue
            found += [parsed] if isinstance(parsed, dict) else []
    return found


def issue_labels(issue: dict) -> list[str] | None:
    """The lower-case labels an issue object lists, only from its `labels` or `fields.labels`; None when it
    has none. Free text is never searched: a ticket's own words could spell a label."""
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
    value = issue.get("labels", fields.get("labels"))
    if not isinstance(value, list):
        return None
    return [str(item.get("name") if isinstance(item, dict) else item).strip().lower() for item in value]


def looks_like_issue(obj: dict) -> bool:
    return any(field in obj for field in ("key", "fields", "labels"))


def on_jira_seen(data: dict) -> None:
    """PostToolUse: the intake is done when this session has read the ticket it waits for and its labels hold
    the label. Anything else leaves it pending, which keeps `approve plan` refused. A response is trusted only
    when exactly one object in it looks like an issue (has `key`, `fields` or `labels`), and it must name the
    ticket by its own `key`: a second object, or one without a key, could be text a ticket's author wrote."""
    wanted = intake_pending(data)
    if wanted is None or not reads_issue(data):
        return
    issues = [obj for obj in issue_objects(data.get("tool_response")) if looks_like_issue(obj)]
    labels = (issue_labels(issues[0]) or []) if len(issues) == 1 else None  # one issue with no list has no labels
    outcome = "nokey" if wanted == NO_KEY else "unreadable" if labels is None else (
        "other" if str(issues[0].get("key", "")).upper() != wanted else "seen" if jira_label().lower() in labels else "missing")
    if outcome == "seen":
        session_file(data, "jira-intake").unlink(missing_ok=True)
        log_event(data, "jira-seen", f"{wanted} label seen")
    emit("PostToolUse", additionalContext=intake_note(wanted, outcome))


def intake_note(wanted: str, outcome: str) -> str:
    """What the chair is told after a read of an issue: `seen`, `missing` (the label), `other` (another ticket) or
    `unreadable` (no single issue with a `labels` list in the response) or `nokey` (the owner's key was not understood)."""
    label = jira_label()
    notes = {
        "seen": f"sdlc-gate: {wanted} was read and its labels hold `{label}`: `approve plan` is no longer held for the intake.",
        "missing": (f"sdlc-gate: {wanted} was read but its labels do not hold `{label}`, so the run stops: write "
                    f"`abandoned: no {label} label` as the last line of status.md (it needs retro.md) and tell the owner."),
        "other": f"sdlc-gate: the issue in this response is not {wanted}; `approve plan` stays held.",
        "nokey": "sdlc-gate: no ticket key was understood in the owner's `/sdlc jira ...`: the owner retypes it, and `approve plan` stays held.",
        "unreadable": ("sdlc-gate: this response could not be read as one Jira issue with a `labels` list, so its label was "
                       "not checked and `approve plan` stays held. Tell the owner; they can reply `sdlc intake off` to go on without the label check (MCP writes stay denied)."),
    }
    return notes[outcome]


def on_mcp(data: dict) -> None:
    reason = mcp_reason(data)
    if reason:
        mark_jira(data)  # so that deleting the run's folder later does not lift it
        deny(reason)
