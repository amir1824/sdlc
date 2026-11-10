#!/usr/bin/env bash
# A small clean project. The merged audit may say PASS only when both agents returned an
# explicit verdict (security-reviewer PASS, leak-scanner CLEAN). In this sandbox both usually
# do, so this case checks the PASS path; no eval forces a missing verdict yet.
set -euo pipefail
cat > greet.py <<'PY'
def greet(name: str) -> str:
    return f"Hello, {name}!"
PY
cat > README.md <<'MD'
# greet
One helper that greets a name.
MD
