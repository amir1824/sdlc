"""Reading a Snyk MCP event for sdlc_gate.py: one scan record from the hook payload, the check on a scan's
arguments and path, and the hash of the code a scan saw. No state is read or written here.

The payload shapes come from a probe of a real Snyk MCP server (2026-11-18): a PostToolUse payload carries
`mcp_server`, an object such as {"name": "Snyk Security", "source": "sdk"} (the display name, with a space; the
tool name spells it Snyk_Security), and a `tool_response` that is a list of text blocks, the first holding the
reply as a JSON string; a PostToolUseFailure payload carries `error` and no `tool_response`. A failure the server reports in plain
text (not authenticated, folder not trusted, product not enabled) arrives as a normal reply, so a reply that
is not a JSON object with `success` true is an error, never an empty result.

ponytail: the IaC finding shape was never recorded from a real reply; its id is built from `id`, `filePath`
and `line`, and a finding without them makes the scan unusable.
ponytail: the hash reads every untracked file that is not ignored, with a 3-second limit on each git call
and none on the reads; a project with a large untracked tree can run past the hook's timeout.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

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
GIT_SECONDS = 3
RUN_FOLDER_PATHSPEC = ":!.sdlc"


def arguments_ok(scanner: str, tool_input: object) -> bool:
    """Whether a scan's arguments are only those that leave the scan whole and its target a path: `command`
    names the program the server runs, `report` writes to Snyk, and `var_file` or `policy_path` read other files."""
    allowed = ALLOWED_ARGUMENTS.get(scanner)
    if allowed is None or not isinstance(tool_input, dict) or not set(tool_input) <= allowed:
        return False
    return all(ARGUMENT_CHECKS[key](value) for key, value in tool_input.items())


def path_inside(path: object, root: str, canon, home: str) -> bool:
    """Whether `path` is the project root or a folder in it, after symlinks. A root that is the home folder
    or `/` is no project."""
    if not isinstance(path, str) or "\x00" in path or not os.path.isabs(path):
        return False
    real_root = canon(root)
    if real_root in (canon(home), canon(os.sep)):
        return False
    return os.path.commonpath([canon(path), real_root]) == real_root


def jira_call_allowed(server: str, name: str, tool_input: object, root: str, canon, home: str, servers) -> bool:
    """Whether a Snyk scan may run in a Jira run: a listed server, one of the three scans, only the safe
    arguments, and a path inside the project."""
    scanner = SCAN_TOOLS.get(name)
    return (server in servers and scanner is not None and arguments_ok(scanner, tool_input)
            and path_inside(tool_input.get("path"), root, canon, home))


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


def full_scan(scanner: str, tool_input: object, root: str, canon) -> bool:
    return (arguments_ok(scanner, tool_input) and isinstance(tool_input.get("path"), str)
            and canon(tool_input["path"]) == canon(root))


def server_name(value: object) -> str | None:
    """The server's name as a tool name spells it (every character outside letters, digits, `_` and `-` is `_`),
    from the payload's `mcp_server`: an object with a `name`, or the name itself."""
    name = value.get("name") if isinstance(value, dict) else value
    return re.sub(r"[^A-Za-z0-9_-]", "_", name) if isinstance(name, str) else None


def record_from_event(event: dict, root: str, tree: str | None, servers, canon) -> tuple[str, dict] | None:
    """(scanner, record) for a Snyk scan event, or None when the event is not a scan from a listed server.
    status is `completed`, `error` (failed, or a reply that is not a count-checked success) or `unusable`
    (the scan was narrowed, the code could not be hashed, or a finding is unreadable)."""
    parts = str(event.get("tool_name", "")).split("__", 2)
    scanner = SCAN_TOOLS.get(parts[2]) if len(parts) == 3 and parts[0] == "mcp" else None
    named = parts[1] if "mcp_server" not in event else server_name(event["mcp_server"])
    if scanner is None or parts[1] not in servers or named != parts[1]:
        return None
    reply = None if event.get("hook_event_name") == "PostToolUseFailure" else reply_object(event.get("tool_response"))
    issues = reply.get("issues") if reply else None
    if not (reply and reply.get("success") is True and isinstance(issues, list) and len(issues) <= MAX_FINDINGS
            and reply.get("issueCount") == len(issues)):
        return scanner, {"status": "error", "tree": tree, "findings": []}
    findings = [finding_of(issue, scanner, root) for issue in issues]
    usable = tree is not None and full_scan(scanner, event.get("tool_input"), root, canon) and None not in findings
    return scanner, {"status": "completed" if usable else "unusable", "tree": tree,
                     "findings": findings if usable else []}


def run_git(root: Path, *args: str) -> bytes | None:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=GIT_SECONDS, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def file_bytes_hash(path: Path) -> bytes:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return b"unreadable"
    return digest.digest()


def tree_hash(root: Path) -> str | None:
    """A hash of HEAD, the diff against it and every untracked file, leaving out `.sdlc/`: the code a scan saw.
    None when git cannot say (not a repo, no commit)."""
    head = run_git(root, "rev-parse", "HEAD")
    diff = run_git(root, "diff", "--no-ext-diff", "--no-textconv", "--no-color", "HEAD", "--", ".", RUN_FOLDER_PATHSPEC)
    names = run_git(root, "ls-files", "-o", "--exclude-standard", "-z", "--", ".", RUN_FOLDER_PATHSPEC)
    if head is None or diff is None or names is None:
        return None
    digest = hashlib.sha256(head + b"\0" + diff)
    for name in sorted(filter(None, names.split(b"\0"))):
        digest.update(name + b"\0" + file_bytes_hash(root / os.fsdecode(name)))
    return digest.hexdigest()
