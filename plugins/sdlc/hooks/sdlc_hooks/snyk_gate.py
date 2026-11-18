"""The Snyk parts of the gate: the project's record, the owner's words, the close gate and the scan record.

The exception is Snyk's three scans (`snyk_code_scan`, `snyk_sca_scan`, `snyk_iac_scan`) from a server named in
SNYK_SERVERS (or in SDLC_SNYK_SERVERS, a comma list the owner sets), with only the arguments in snyk/events.py and a
`path` that is the project or a folder in it, after symlinks, in a project that is not the home folder or `/`, and
only where the owner typed `sdlc snyk on` (the consent to upload the source): they send the project's files to Snyk,
not a ticket's text. Every other Snyk tool, `snyk_auth` and `snyk_trust`
included, stays denied. Any error while deciding denies.
`snyk-seen` (PostToolUse and PostToolUseFailure, matcher on Snyk's scan tools): records the scan in
`sdlc-gate/snyk/<project>.json` (status, the hash of the code it saw, its findings), one record per kind of scan,
the newest replacing the last. A scan that was not of the whole project, or whose reply is not a JSON success
with a matching count, is recorded as unusable or error, never as an empty result.
The Snyk gate (in `prompt` and `tool`): the owner types `sdlc snyk on|off` for a project (`on` is the consent to upload
its source; it pins the base commit when Snyk was not already on, and so does the first plan approval when none is
pinned), `sdlc snyk accept F<n> <reason>` for one finding, and `sdlc snyk waive <reason>` for an incomplete gate on the
code as it is now. Only the owner's typed words reach `prompt`; the slash form `/sdlc snyk on` is the host's /sdlc
command and starts a run. With Snyk on, a Write, Edit or MultiEdit of `.sdlc/<run>/status.md` (in any case, through a
symlink, or as a hard link) that leaves the run closed or Ship running or done is denied unless security_gate.py says
PASS (or INCOMPLETE and waived); a Bash command that names a status.md is denied; and in every project a Bash
command that types `sdlc snyk on|off|accept|waive` is denied, so a child `claude -p` cannot speak as the owner. A record that cannot be read, a base that is not a commit, git failing or too slow (one 3.5-second budget for
the changed files and the hash, under the hook's 5-second timeout), or an error while checking all hold the gate. Snyk
off or undecided changes nothing, and a broken module cannot touch such a project.
ponytail: Bash that builds the path at run time or runs a script, another tool, or an edit outside the host can still write status.md;
the gate stops a model's slip, not one set on getting past it, and is not a merge protection: a commit made outside
`/sdlc` never meets it. The base stays where it was pinned until the owner turns Snyk off and on again, so a later run
in the same project is judged against the old base (more files count as changed: the safe side). The owner's commands
and `snyk-seen` read, change and write the record with no lock, so two at the same moment can lose one change (a scan
record the gate then calls missing, or, rarely, a policy it then calls undecided).
ponytail: a server's name is configuration, not identity: another server given an allowed name would be believed.
A scan still uploads the project's source and dependency list to Snyk, and a Snyk server not named in
SNYK_SERVERS is denied in a Jira run and not recorded anywhere.
"""
from __future__ import annotations

import functools
import importlib.util
import re
from pathlib import Path
from typing import Callable, NamedTuple

from sdlc_hooks.bash.parse import writes_files
from sdlc_hooks.core import canonical, emit, log_event, now, project_root, written_relative
from sdlc_hooks.snyk_state import POLICY_ON, read_snyk_state, snyk_required, snyk_servers, snyk_state_of, snyk_state_path, write_snyk_state

SNYK_OWNER_WORDS = re.compile(r"sdlc\s+snyk\s+(?:on|off|accept|waive)\b", re.IGNORECASE)
SNYK_TAG = "sdlc-gate (Snyk gate): "

GATE_FOLDER_NAME = "sdlc-gate"

STATUS_FILE_NAME = "status.md"


@functools.cache
def load_sibling(name: str):
    """A module of the hooks folder (`snyk/events` for one in a subfolder), loaded by its file path: `python3 -I` leaves
    the folder off sys.path. Loaded once per run of the hook."""
    path = Path(__file__).resolve().parents[1] / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("/", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snyk_answer(text: str) -> None:
    emit("UserPromptSubmit", additionalContext=f"sdlc-gate: {text}")


class SnykHost(NamedTuple):
    """What the modules in snyk/ may use of this file (they are loaded by path and import nothing from it): the
    project of an event (and its root), the project's record, a line to the owner, the approvals log, the path of a
    write relative to the project, the loader of sibling modules, and the clock."""
    project: Callable
    root: Callable
    read_state: Callable
    write_state: Callable
    say: Callable
    log_event: Callable
    written_relative: Callable
    load: Callable
    now: Callable


def snyk_host() -> SnykHost:
    events = load_sibling("snyk/events")

    def project(data: dict):
        return events.Project(str(project_root(data)), canonical, str(Path.home()), snyk_servers())

    return SnykHost(project, project_root, lambda root: read_snyk_state(snyk_state_path(root)),
                    lambda root, state: write_snyk_state(snyk_state_path(root), state), snyk_answer, log_event,
                    written_relative, load_sibling, now)


def snyk_scan_allowed(data: dict, call: tuple) -> bool:
    """Whether a Snyk scan, `call` being (server, tool name, tool input), may run in a Jira run (see the module
    docstring): the owner typed `sdlc snyk on` for the project, which is the consent to upload its source. Any error
    is a no."""
    try:
        if snyk_state_of(data)["policy"] != POLICY_ON:
            return False
        events = load_sibling("snyk/events")
        return events.jira_call_allowed(events.McpCall(*call), snyk_host().project(data))
    except Exception:  # fail closed: a scan that cannot be judged does not run
        return False


def on_snyk_seen(data: dict) -> None:
    """PostToolUse and PostToolUseFailure: record a Snyk scan of this project in the project's state."""
    load_sibling("snyk/record").record_scan(snyk_host(), data)


def pin_snyk_base(root: Path) -> None:
    try:
        load_sibling("snyk/record").pin_base(snyk_host(), root)
    except Exception:  # a failed pin must not stop an approval; the gate then reports the change as unknown
        return


def on_snyk_command(data: dict, text: str) -> None:
    """The owner's `sdlc snyk on|off|accept|waive`: only typed words reach UserPromptSubmit."""
    try:
        load_sibling("snyk/owner").run(snyk_host(), data, text)
    except Exception as error:  # an error before the record is written leaves it as it was; the log comes after it
        snyk_answer(f"`sdlc snyk` could not finish ({type(error).__name__}); type it again.")


def snyk_close_reason(data: dict, tool: str, tool_input: object) -> str:
    """Why a write to a run's status.md may not close the run or start Ship: Snyk is on for the project and the gate
    is not closable. A project with Snyk off or undecided is not looked at, so a broken module cannot touch it; in one
    with Snyk on, any error while checking holds the write."""
    state = snyk_state_of(data)
    if not snyk_required(state):
        return ""
    try:
        guard = load_sibling("snyk/guard")
        text = guard.close_reason(snyk_host(), guard.ToolCall(data, tool, tool_input), state)
    except Exception as error:  # fail closed: a gate that cannot be checked is not passed
        text = (f"this write could not be checked ({type(error).__name__}), so it is held. The owner types "
                "`sdlc snyk off` to stop requiring Snyk in this project.")
    return f"{SNYK_TAG}{text}" if text else ""


def snyk_bash_reason(data: dict, command: str) -> str:
    """The owner's `sdlc snyk` words in a Bash command (a child `claude -p` would be read as the owner) are denied in
    every project. With Snyk on, so is any command that names a status.md (the gate cannot read what a command leaves
    there, and Read, Grep and Write do the job) and any command that writes and names the gate's folder, which holds
    the record (a `cd` and a relative path would not spell its full path). It is a check on names: a path built at run
    time is not seen."""
    if SNYK_OWNER_WORDS.search(command):
        return (f"{SNYK_TAG}a Bash command that holds the words `sdlc snyk on|off|accept|waive` is denied: the owner "
                "types them in the prompt. To search for them use a pattern that stops before the verb; to put them "
                "in a commit message use `git commit -F <file>`.")
    if not snyk_required(snyk_state_of(data)):
        return ""
    named = command.casefold()
    if STATUS_FILE_NAME in named:
        return (f"{SNYK_TAG}a Bash command that names a status.md is denied while Snyk is required, since the gate "
                "cannot read what it leaves. Read it with Read or Grep and write it with Write; to keep the name out "
                "of a commit message, use `git commit -F <file>`.")
    if GATE_FOLDER_NAME in named and writes_files(command):
        return (f"{SNYK_TAG}a Bash command that writes and names the gate's folder is denied while Snyk is required: "
                "the folder holds the record of the owner's decisions. To put the name in a commit message, use "
                "`git commit -F <file>`.")
    return ""
