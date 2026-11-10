#!/usr/bin/env bash
set -euo pipefail
cat > text.py <<'PY'
def title_case(text: str) -> str:
    return text.title()
PY
