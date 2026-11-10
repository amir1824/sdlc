#!/usr/bin/env bash
set -euo pipefail
cat > pagination.py <<'PY'
def paginate(items: list, page: int, size: int) -> list:
    start = page * size
    return items[start:start + size]
PY
cat > report.py <<'PY'
from pagination import paginate

def r(d, p, s):
    x = []
    for i in paginate(d, p, s):
        x.append(str(i).strip().upper())
    out = ""
    for y in x:
        out = out + y + ","
    return out
PY
cat > test_pagination.py <<'PY'
from pagination import paginate

def test_page_has_at_most_size_items():
    assert len(paginate(list(range(10)), 2, 3)) <= 3
PY
