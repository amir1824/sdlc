#!/usr/bin/env bash
set -euo pipefail
cat > validate.py <<'PY'
def parse_age(raw: str) -> int:
    age = int(raw)
    if age < 0 or age > 150:
        raise ValueError(f"age out of range: {age}")
    return age
PY
cat > profile.py <<'PY'
from validate import parse_age

def build_profile(name: str, raw_age: str) -> dict:
    return {"name": name, "age": parse_age(raw_age)}
PY
cat > test_validate.py <<'PY'
import pytest
from validate import parse_age

def test_valid_age():
    assert parse_age("30") == 30

def test_out_of_range_raises():
    with pytest.raises(ValueError):
        parse_age("200")
PY
