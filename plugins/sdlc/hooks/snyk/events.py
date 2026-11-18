"""Reading a Snyk MCP event for sdlc_gate.py: one scan record from the hook payload, and the check on a scan's
arguments and path. No state is read or written here.

The payload shapes come from a probe of a real Snyk MCP server (2026-11-18): a PostToolUse payload carries
`mcp_server`, an object such as {"name": "Snyk Security", "source": "sdk"} (the display name, with a space; the
tool name spells it Snyk_Security), and a `tool_response` that is a list of text blocks, the first holding the
reply as a JSON string; a PostToolUseFailure payload carries `error` and no `tool_response`. A failure the server reports in plain text
(not authenticated, folder not trusted, product not enabled) arrives as a normal reply, so a reply that is not a
JSON object with `success` true is an error, never an empty result.

The hash of the code a scan saw, and the changed files, are in tree.py.
ponytail: the IaC finding shape was never recorded from a real reply; its id is built from `id`, `filePath`
and `line`, and a finding without them makes the scan unusable.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable, NamedTuple

SCAN_TOOLS = {"snyk_code_scan": "code", "snyk_sca_scan": "sca", "snyk_iac_scan": "iac"}
ALLOWED_ARGUMENTS = {
    "code": frozenset({"path", "severity_threshold"}),
    "sca": frozenset({"path", "severity_threshold", "all_projects", "command"}),
    "iac": frozenset({"path", "severity_threshold"}),
}
PYTHON_PROGRAMS = frozenset({"python3", "python"})
ARGUMENT_CHECKS = {
    "path": lambda value: isinstance(value, str),
    "severity_threshold": lambda value: value == "high",  # a threshold that is lower hides nothing; none is also fine
    "all_projects": lambda value: isinstance(value, bool),
    "command": lambda value: isinstance(value, str) and value in PYTHON_PROGRAMS,
}
MAX_FINDINGS = 2000
MAX_REPLY_CHARS = 2_000_000


class Project(NamedTuple):
    """The project a scan belongs to, and what the checks on it need from the host: `canonical` resolves a path to one
    spelling, `servers` are the Snyk server names the owner allows."""
    root: str
    canonical: Callable[[str], str]
    home: str
    servers: frozenset


class McpCall(NamedTuple):
    server: str
    name: str
    tool_input: object


def arguments_ok(scanner: str, tool_input: object) -> bool:
    """Whether a scan's arguments are only those that leave the scan whole and its target a path: `command`
    names the program the server runs, `report` writes to Snyk, and `var_file` or `policy_path` read other files."""
    allowed = ALLOWED_ARGUMENTS.get(scanner)
    if allowed is None or not isinstance(tool_input, dict) or not set(tool_input) <= allowed:
        return False
    return all(ARGUMENT_CHECKS[key](value) for key, value in tool_input.items())


def path_inside(path: object, project: Project) -> bool:
    """Whether `path` is the project root or a folder in it, after symlinks. A root that is the home folder
    or `/` is no project."""
    if not isinstance(path, str) or "\x00" in path or not os.path.isabs(path):
        return False
    real_root = project.canonical(project.root)
    if real_root in (project.canonical(project.home), project.canonical(os.sep)):
        return False
    return os.path.commonpath([project.canonical(path), real_root]) == real_root


def jira_call_allowed(call: McpCall, project: Project) -> bool:
    """Whether a Snyk scan may run in a Jira run: a listed server, one of the three scans, only the safe
    arguments, and a path inside the project."""
    scanner = SCAN_TOOLS.get(call.name)
    return (call.server in project.servers and scanner is not None and arguments_ok(scanner, call.tool_input)
            and path_inside(call.tool_input.get("path"), project))


def reply_object(response: object) -> dict | None:
    """The JSON object a reply holds, from a list of text blocks, a mapping with `content`, or a string."""
    blocks = response if isinstance(response, list) else [response]
    if isinstance(response, dict) and isinstance(response.get("content"), list):
        blocks = response["content"]
    for block in blocks:
        text = block.get("text") if isinstance(block, dict) else block
        if isinstance(text, str) and len(text) <= MAX_REPLY_CHARS and text.lstrip()[:1] == "{":
            try:
                parsed = json.loads(text)
            except (ValueError, RecursionError):
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def relative(path: str, root: str) -> str:
    real_root = os.path.realpath(root)
    real = os.path.realpath(path) if os.path.isabs(path) else path
    return os.path.relpath(real, real_root).replace(os.sep, "/") if real.startswith(real_root + os.sep) else path


def finding_of(issue: object, scanner: str, root: str) -> dict | None:
    """One finding in the gate's shape, or None when the issue lacks what the gate needs."""
    if not isinstance(issue, dict):
        return None
    ident = {"code": issue.get("fingerPrint"),
             "sca": f"{issue.get('id')}@{issue.get('packageName')}@{issue.get('version')}",
             "iac": f"{issue.get('id')}@{issue.get('filePath')}:{issue.get('line')}"}[scanner]
    file, severity = issue.get("filePath"), issue.get("severity")
    steps = issue.get("dataflow") if scanner == "code" and isinstance(issue.get("dataflow"), list) else []
    flow = [step.get("filePath") for step in steps if isinstance(step, dict)]
    if not (isinstance(ident, str) and isinstance(file, str) and isinstance(severity, str)
            and all(isinstance(step, str) for step in flow)):
        return None
    return {"id": ident, "severity": severity.lower(), "kind": scanner, "file": relative(file, root),
            "flow": [relative(step, root) for step in flow]}


def full_scan(scanner: str, tool_input: object, project: Project) -> bool:
    """A scan of the project root that covers every project in it (a dependency scan without `all_projects` reads
    only the root's manifest)."""
    return (arguments_ok(scanner, tool_input) and isinstance(tool_input.get("path"), str)
            and project.canonical(tool_input["path"]) == project.canonical(project.root)
            and (scanner != "sca" or tool_input.get("all_projects") is True))


def server_name(value: object) -> str | None:
    """The server's name as a tool name spells it (every character outside letters, digits, `_` and `-` is `_`),
    from the payload's `mcp_server`: an object with a `name`, or the name itself."""
    name = value.get("name") if isinstance(value, dict) else value
    return re.sub(r"[^A-Za-z0-9_-]", "_", name) if isinstance(name, str) else None


def record_from_event(event: dict, project: Project, tree: str | None) -> tuple[str, dict] | None:
    """(scanner, record) for a Snyk scan event, or None when the event is not a scan from a listed server.
    status is `completed`, `error` (failed, or a reply that is not a count-checked success) or `unusable`
    (the scan was narrowed, the code could not be hashed, or a finding is unreadable)."""
    parts = str(event.get("tool_name", "")).split("__", 2)
    scanner = SCAN_TOOLS.get(parts[2]) if len(parts) == 3 and parts[0] == "mcp" else None
    named = parts[1] if "mcp_server" not in event else server_name(event["mcp_server"])
    if scanner is None or parts[1] not in project.servers or named != parts[1]:
        return None
    reply = None if event.get("hook_event_name") == "PostToolUseFailure" else reply_object(event.get("tool_response"))
    issues = reply.get("issues") if reply else None
    if not (reply and reply.get("success") is True and isinstance(issues, list) and len(issues) <= MAX_FINDINGS
            and reply.get("issueCount") == len(issues)):
        return scanner, {"status": "error", "tree": tree, "findings": []}
    findings = [finding_of(issue, scanner, project.root) for issue in issues]
    usable = tree is not None and full_scan(scanner, event.get("tool_input"), project) and None not in findings
    return scanner, {"status": "completed" if usable else "unusable", "tree": tree,
                     "findings": findings if usable else []}
