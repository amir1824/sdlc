"""Where things are, for every test: the repository, the hooks folder and the gate script."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOOKS = REPO / "plugins" / "sdlc" / "hooks"
SCRIPT = HOOKS / "sdlc_gate.py"
