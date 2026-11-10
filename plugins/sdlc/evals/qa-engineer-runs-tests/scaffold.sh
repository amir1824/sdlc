#!/usr/bin/env bash
set -euo pipefail
cat > discount.py <<'PY'
def discount(total: float) -> float:
    if total > 100:
        return total * 0.9
    return total
PY
cat > test_discount.py <<'PY'
from discount import discount

def test_below_threshold_has_no_discount():
    assert discount(50) == 50

def test_above_threshold_is_discounted():
    assert discount(200) == 180
PY
