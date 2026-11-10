#!/usr/bin/env bash
set -euo pipefail
cat > users.py <<'PY'
USERS = {1: "Dana", 2: "Lee"}
EMAILS = {1: "dana@example.com", 2: "lee@example.com"}

def get_user_name(user_id: int) -> str | None:
    return USERS.get(user_id)
PY
cat > test_users.py <<'PY'
from users import get_user_name

def test_known_user():
    assert get_user_name(1) == "Dana"

def test_unknown_user_is_none():
    assert get_user_name(99) is None
PY
