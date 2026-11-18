"""The run fingerprint for `status_check.py fingerprint`: it runs the one definition, the block under `### Fingerprint`
in commands/sdlc.md, with the header's `base:`, so the prompt and the code cannot drift apart.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

COMMAND_FILE = Path(__file__).resolve().parents[3] / "commands" / "sdlc.md"
BLOCK = re.compile(r"### Fingerprint.*?```sh\n(.*?)\n```", re.DOTALL)
BASE_LINE = re.compile(r"base: ([0-9a-f]{40,64})")
SECONDS = 30
ERROR_SHOWN = 200


def fingerprint_command() -> str:
    found = BLOCK.search(COMMAND_FILE.read_text(encoding="utf-8"))
    if found is None:
        raise ValueError(f"no `### Fingerprint` block in {COMMAND_FILE}")
    return found.group(1)


def run_fingerprint(status: Path, base: str) -> str:
    """What the block prints (`<sha256>  -` and a newline), run from the run's folder, which sits in the repository."""
    done = subprocess.run(["bash", "-c", fingerprint_command()], cwd=status.parent, capture_output=True, text=True,
                          timeout=SECONDS, env={**os.environ, "BASE": base})
    if done.returncode != 0:
        raise ValueError(f"the fingerprint command failed: {done.stderr.strip()[:ERROR_SHOWN]}")
    return done.stdout


def print_fingerprint(status: Path, read_lines: Callable[[Path], list[str]]) -> int:
    """The CLI: print the fingerprint of the run whose status.md this is, using the header's `base:`; 2 when it cannot."""
    try:
        bases = [found[1] for found in map(BASE_LINE.fullmatch, read_lines(status)) if found]
        if not bases:
            raise ValueError(f"{status} has no `base: <commit>` line")
        print(run_fingerprint(status, bases[0]), end="")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"status_check: {error}", file=sys.stderr)
        return 2
    return 0
