"""The code a Snyk scan saw, for sdlc_hooks/snyk_gate.py: a hash of it, and the files that differ from a base commit.

The hash and the list share one Budget (3.5 seconds, below the 5-second hook timeout, which the host reads as allow,
and 256 MiB of untracked content): a budget that runs out, or git failing, raises TreeUnavailable with the reason,
which `collect` turns into the gate's "not hashed" or "change unknown" plus that reason, never into a pass. A symlink is hashed as its target's name, and a device or pipe is never opened, so
`ln -s /dev/zero pad` cannot hold the hook.
A tracked file marked assume-unchanged or skip-worktree is hashed by its content (a link by its target), and listed as
changed when it differs from the base (`git diff` never shows an edit of one).
ponytail: the hash does not see a dirty submodule's content, a nested git repo, paths hidden by .git/info/exclude,
or what a tracked symlink points at; the upgrade is `git submodule status` in the hash input. It is taken after the
scan, so code changed during a scan is in it.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import time
from pathlib import Path

GIT_SECONDS = 3
HOOK_BUDGET_SECONDS = 3.5
MAX_HASH_BYTES = 256 * 1024 * 1024
READ_CHUNK = 1 << 20
RUN_FOLDER = ".sdlc"
RUN_FOLDER_PATHSPEC = ":!" + RUN_FOLDER
HASHING_BUDGET_SPENT = "time or byte budget spent while hashing untracked files"
COMMIT_HASH = re.compile(r"[0-9a-f]{40,64}")


class TreeUnavailable(Exception):
    """Git cannot say, or the budget ran out; the message says which."""


class Budget:
    """Time and bytes one hook run may spend on git and on reading files, and what that run reads once: the listing of
    flagged files, because the code does not change while one hook run is going. Never reuse one across runs."""

    def __init__(self, seconds: float, max_bytes: int = MAX_HASH_BYTES):
        self.end = time.monotonic() + seconds
        self.bytes_left = max_bytes
        self.flagged: list[str] | None = None  # the listing of flagged files, read once per run

    def seconds_left(self) -> float:
        return self.end - time.monotonic()

    def take(self, size: int) -> bool:
        """Spend `size` bytes; False when the bytes or the time are gone."""
        self.bytes_left -= size
        return self.bytes_left >= 0 and self.seconds_left() > 0


def new_budget() -> Budget:
    return Budget(HOOK_BUDGET_SECONDS)


def run_git(root: Path, *args: str, budget: Budget | None = None, stdin: bytes | None = None) -> bytes:
    seconds = min(GIT_SECONDS, (budget or Budget(GIT_SECONDS)).seconds_left())
    if seconds <= 0:
        raise TreeUnavailable("time budget spent")
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=seconds, check=True, input=stdin).stdout
    except subprocess.TimeoutExpired:
        raise TreeUnavailable(f"git {args[0]} timed out") from None
    except (OSError, subprocess.SubprocessError):
        raise TreeUnavailable(f"git {args[0]} failed") from None


def file_digest(path: Path, budget: Budget) -> bytes:
    """The hash of a regular file's content; TreeUnavailable when the budget runs out while reading it."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(READ_CHUNK), b""):
                digest.update(chunk)
                if not budget.take(len(chunk)):
                    raise TreeUnavailable(HASHING_BUDGET_SPENT)
    except OSError:
        return b"unreadable"
    return digest.digest()


def entry_digest(path: Path, budget: Budget) -> bytes:
    """What one untracked path adds to the hash: a link by its target's name, a regular file by its content, anything
    else (a device, a pipe, a socket, a nested repo's folder) by its kind, never opened."""
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            return b"link:" + os.fsencode(os.readlink(path))
    except OSError:
        return b"missing"
    return file_digest(path, budget) if stat.S_ISREG(mode) else b"special"


def flagged_files(root: Path, budget: Budget) -> list[str]:
    """Tracked files git was told not to look at (assume-unchanged shows as a lowercase tag, skip-worktree as `S`)
    that are on disk: `git diff` and `git status` never list an edit of one."""
    if budget.flagged is None:
        listing = run_git(root, "ls-files", "-v", "-z", "--", ".", RUN_FOLDER_PATHSPEC, budget=budget)
        flagged = (os.fsdecode(entry[2:]) for entry in listing.split(b"\0") if entry[:1].islower() or entry[:1] == b"S")
        budget.flagged = sorted(name for name in flagged if os.path.lexists(root / name))
    return budget.flagged


def current_hashes(root: Path, names: list[str], budget: Budget) -> dict[str, bytes]:
    """The blob hash each of `names` would have: a regular file by its content (one git call for all), a link by its
    target's text (one call each, from stdin: `git hash-object` on the path would follow it). Anything else, a name with a
    line break (the line protocol of git cannot carry it) and a file gone since it was listed has no hash."""
    kinds: dict[str, list[str]] = {"file": [], "link": []}
    for name in names:
        try:
            mode = os.lstat(root / name).st_mode
        except OSError:
            continue
        if "\n" not in name and (stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
            kinds["file" if stat.S_ISREG(mode) else "link"].append(name)
    found = {}
    if kinds["file"]:
        hashes = run_git(root, "hash-object", "--stdin-paths", budget=budget, stdin=os.fsencode("\n".join(kinds["file"]))).split()
        if len(hashes) != len(kinds["file"]):
            raise TreeUnavailable("git hash-object gave an answer of the wrong length")
        found.update(zip(kinds["file"], hashes))
    for name in kinds["link"]:
        found[name] = run_git(root, "hash-object", "--stdin", budget=budget, stdin=os.fsencode(os.readlink(root / name))).strip()
    return found


def differing_files(root: Path, base: str, names: list[str], budget: Budget) -> set[str]:
    """The files among `names` that are not the blob `base` holds (a file `base` lacks differs), in two git calls for
    the regular files. A device, a pipe, a file gone since it was listed and a name with a line break differ without being
    opened (`git hash-object` would follow a link to `/dev/zero` until the budget ran out)."""
    current = current_hashes(root, names, budget)
    if not current:
        return set(names)
    in_base = run_git(root, "cat-file", "--batch-check", budget=budget,
                      stdin=os.fsencode("".join(f"{base}:./{name}\n" for name in current))).splitlines()
    if len(in_base) != len(current):
        raise TreeUnavailable("git cat-file gave an answer of the wrong length")
    same = {name for (name, now), held in zip(current.items(), in_base) if held.split()[:2] == [now, b"blob"]}
    return set(names) - same


def head_commit(root: Path) -> str:
    """The hash of HEAD; TreeUnavailable when there is no repo or no commit."""
    return run_git(root, "rev-parse", "HEAD").decode().strip()


def tree_hash(root: Path, budget: Budget | None = None) -> str:
    """A hash of HEAD, the diff against it and every untracked file, leaving out `.sdlc/`: the code a scan saw.
    TreeUnavailable when git cannot say (not a repo, no commit) or the budget runs out."""
    budget = budget or new_budget()
    head = run_git(root, "rev-parse", "HEAD", budget=budget)
    diff = run_git(root, "diff", "--no-ext-diff", "--no-textconv", "--no-color", "HEAD", "--", ".",
                   RUN_FOLDER_PATHSPEC, budget=budget)
    names = run_git(root, "ls-files", "-o", "--exclude-standard", "-z", "--", ".", RUN_FOLDER_PATHSPEC, budget=budget)
    digest = hashlib.sha256(head + b"\0" + diff)
    for name in sorted(filter(None, names.split(b"\0"))):
        if budget.seconds_left() <= 0:
            raise TreeUnavailable(HASHING_BUDGET_SPENT)
        digest.update(name + b"\0" + entry_digest(root / os.fsdecode(name), budget))
    for name in flagged_files(root, budget):
        if budget.seconds_left() <= 0:
            raise TreeUnavailable(HASHING_BUDGET_SPENT)
        digest.update(b"flagged\0" + os.fsencode(name) + b"\0" + entry_digest(root / name, budget))
    return digest.hexdigest()


def changed_files(root: Path, base: object, budget: Budget | None = None) -> list[str]:
    """The files that differ from commit `base`, tracked or not, without `.sdlc/`, named relative to `root` (a project
    that is a folder of a larger repo); a renamed file is listed under both names. TreeUnavailable when `base` is not
    a commit hash, git cannot say, or the budget runs out."""
    if not isinstance(base, str) or not COMMIT_HASH.fullmatch(base):
        raise TreeUnavailable("no base commit is pinned")
    budget = budget or new_budget()
    tracked = run_git(root, "diff", "--name-only", "-z", "--no-renames", "--relative", base, "--", ".",
                      RUN_FOLDER_PATHSPEC, budget=budget)
    untracked = run_git(root, "ls-files", "-o", "--exclude-standard", "-z", "--", ".", RUN_FOLDER_PATHSPEC,
                        budget=budget)
    listed = {os.fsdecode(name) for name in (tracked + b"\0" + untracked).split(b"\0") if name}
    return sorted(listed | differing_files(root, base, flagged_files(root, budget), budget))


def collect(root: Path, base: object, budget: Budget) -> tuple[list[str] | None, str | None, tuple[str, ...]]:
    """(changed files, hash of the code, notes) for the gate; what git cannot say is None, with the reason in the notes."""
    notes = []
    try:
        changed = changed_files(root, base, budget)
    except TreeUnavailable as error:
        changed = None
        notes.append(f"changed files: {error}")
    try:
        code = tree_hash(root, budget)
    except TreeUnavailable as error:
        code = None
        notes.append(f"code hash: {error}")
    return changed, code, tuple(notes)
