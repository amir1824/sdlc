#!/usr/bin/env bash
# Usage: compare-golden.sh <restructured shop dir>
# Prints "ok" when the public API of that copy gives the same answers as the pristine fixture on the
# whole input grid of golden.mjs, otherwise how many of the answers differ.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pristine="$(mktemp -d)"
(cd "$pristine" && bash "$here/shop-fixture.sh")
node "$here/golden.mjs" "$pristine" > "$pristine/expected.json"
if ! node "$here/golden.mjs" "$1" > "$pristine/actual.json" 2> "$pristine/err.txt"; then echo "broken: $(head -c 200 "$pristine/err.txt")"; exit 0; fi
python3 -I - "$pristine/expected.json" "$pristine/actual.json" <<'PY'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
bad = [k for k in a if a[k] != b.get(k)]
print("ok" if not bad else f"{len(bad)} of {len(a)} answers differ, e.g. {bad[0]}")
PY
