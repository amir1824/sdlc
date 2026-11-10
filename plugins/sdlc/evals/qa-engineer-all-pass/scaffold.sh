#!/usr/bin/env bash
set -euo pipefail
cat > discount.py <<'PY'
def discount(total: float) -> float:
    if total >= 100:
        return total * 0.9
    return total
PY
cat > test_discount.py <<'PY'
from discount import discount

def test_just_below_threshold():
    assert discount(99) == 99

def test_at_threshold():
    assert discount(100) == 90

def test_above_threshold():
    assert discount(200) == 180
PY
