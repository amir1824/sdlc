#!/usr/bin/env bash
set -euo pipefail
cat > emailcheck.py <<'PY'
def is_valid(email: str) -> bool:
    return "@" in email
PY
cat > test_emailcheck.py <<'PY'
from emailcheck import is_valid

def test_normal_address():
    assert is_valid("dana@example.com")
PY
