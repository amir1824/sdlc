"""Why a Bash command may not run now: the write checks and the commit check, per agent.
"""
from __future__ import annotations

from sdlc_hooks.bash.commits import commit_reason
from sdlc_hooks.bash.parse import spells_state, too_long, writes_files, writes_state
from sdlc_hooks.bash.patterns import MAX_CHECKED_COMMAND
from sdlc_hooks.core import agent_name, project_root
from sdlc_hooks.files.checks import lock_reason

READ_ONLY_AGENTS = {"tech-lead", "security-reviewer", "brutal-reviewer", "analyst", "leak-scanner"}


def write_reason(data: dict, command: str) -> str:
    """Why a command that writes may not run now: the gate's state is the owner's, and the lock holds
    for Bash as it does for the file tools. A command that neither spells the state nor meets a lock is not read."""
    names_state = spells_state(command)
    if len(command) <= MAX_CHECKED_COMMAND and not names_state and not writes_files(command, scratch_ok=True):
        return ""
    lock_denial = lock_reason(data, project_root(data))
    if not (names_state or lock_denial):
        return ""
    long_command = too_long(command, "the gate's state or an unapproved plan is in play")
    if long_command:
        return long_command
    if names_state and writes_state(command):
        return "sdlc-gate: the gate's state belongs to the owner; do not change it from Bash."
    if lock_denial and writes_files(command, scratch_ok=True):
        return (f"{lock_denial} A Bash command that writes is denied too, except a redirect into /tmp: use the "
                "Write tool for files under .sdlc/ (it creates the folders).")
    return ""


def bash_reason(data: dict, command: str) -> str:
    agent = agent_name(data)
    read_only = agent in READ_ONLY_AGENTS
    if not read_only:
        return commit_reason(command, str(data.get("cwd", ""))) or write_reason(data, command)
    reason = too_long(command, f"{agent} is read-only") or commit_reason(command, str(data.get("cwd", "")))
    if reason:
        return reason
    if writes_files(command):
        return (f"sdlc-gate: {agent} is read-only, and this command can change files or git state. "
                "Use read-only commands (git diff, git log, grep, the scanners).")
    return ""
