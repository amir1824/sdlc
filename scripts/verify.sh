#!/usr/bin/env bash
# The local gate for this repo, in place of a CI job: check.sh (install drift, versions, lessons,
# frozen evals) and the unit tests, in one foreground process. Both always run, so one failure does
# not hide the other. Exits non-zero when either fails. Extra arguments go to unittest, e.g.
# `scripts/verify.sh -k gate`.
set -uo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
failed=""

echo "== check.sh"
bash "$repo/scripts/check.sh" || failed="check.sh"

echo "== unit tests"
(cd "$repo" && python3 -I -m unittest discover -s tests "$@") || failed="${failed:+$failed, }unit tests"

if [ -n "$failed" ]; then
  echo "verify: FAILED ($failed)"
  exit 1
fi
echo "verify: ok"
