"""The project's Snyk record: where it is kept, how it is read and written, and the servers the owner allows.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from sdlc_hooks.core import canonical, project_root, state_dir

POLICY_ON, POLICY_OFF, POLICY_UNREADABLE = "on", "off", "unreadable"  # as in security_gate.py; a test holds them equal

STATE_KEY_CHARS = 32


def snyk_servers() -> frozenset[str]:
    named = os.environ.get("SDLC_SNYK_SERVERS", "")
    return frozenset({"Snyk_Security", *filter(None, (word.strip() for word in named.split(",")))})


def snyk_state_path(root: Path) -> Path:
    return state_dir() / "snyk" / f"{hashlib.sha256(canonical(root).encode()).hexdigest()[:STATE_KEY_CHARS]}.json"


def empty_snyk_state(policy: str | None = None) -> dict:
    return {"policy": policy, "scans": {}, "accepted": [], "waived": [], "base": None, "log": []}


def read_snyk_state(path: Path) -> dict:
    """The project's Snyk record. A file that is not there is an empty record; one that is there and cannot be read
    has the policy `unreadable`, which the gate treats as on and incomplete until the owner types `sdlc snyk on|off`.
    Never raises."""
    try:
        loaded = json.loads(path.read_text())
    except FileNotFoundError:
        return empty_snyk_state()
    except Exception:  # OSError, bad JSON, and RecursionError from nesting too deep: none may stop the owner's repair
        return empty_snyk_state(POLICY_UNREADABLE)
    ok = isinstance(loaded, dict) and isinstance(loaded.get("scans"), dict)
    return {**empty_snyk_state(), **loaded} if ok else empty_snyk_state(POLICY_UNREADABLE)


def snyk_required(state: dict) -> bool:
    return state["policy"] not in (None, POLICY_OFF)


def write_snyk_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(state))
    os.replace(temp, path)


def snyk_state_of(data: dict) -> dict:
    return read_snyk_state(snyk_state_path(project_root(data)))
