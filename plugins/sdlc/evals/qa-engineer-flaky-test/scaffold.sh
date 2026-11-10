#!/usr/bin/env bash
set -euo pipefail
cat > ids.py <<'PY'
import random

def new_id() -> float:
    return random.random()
PY
cat > test_ids.py <<'PY'
from ids import new_id

def test_id_is_in_the_lower_half():
    assert new_id() < 0.5

def test_id_is_a_number():
    assert isinstance(new_id(), float)
PY
