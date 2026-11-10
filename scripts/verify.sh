#!/usr/bin/env bash
# The local gate for this repo, in place of a CI job: check.sh (install drift, versions, lessons,
# frozen evals) and the unit tests, in one foreground process. Both always run, so one failure does
# not hide the other. Exits non-zero when either fails. Extra arguments go to unittest, e.g.
# `scripts/verify.sh -k gate`.
#
# `scripts/verify.sh --evals [claude plugin eval options]` then runs the plugin's eval cases
# (plugins/sdlc/evals) against the files in this repo. That calls the model and costs money, so it
# never runs without the flag and stops at SDLC_EVAL_MAX_USD (default 5). SDLC_EVAL_THRESHOLD
# (default 0.8) is the score a run must reach. Narrow it with the eval's own options, e.g.
# `scripts/verify.sh --evals --case 'tech-lead-*' --runs 3`. The gate hook is off for the eval
# sessions (SDLC_GATE=off): the cases answer no approval prompt, so a locked session would block Build.
set -uo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
failed=""
evals=""
if [ "${1:-}" = "--evals" ]; then
  evals=yes
  shift
fi

echo "== check.sh"
SDLC_EVALS="${SDLC_EVALS:-$repo/plugins/sdlc/evals}" bash "$repo/scripts/check.sh" || failed="check.sh"

echo "== unit tests"
if [ -n "$evals" ]; then
  (cd "$repo" && python3 -I -m unittest discover -s tests) || failed="${failed:+$failed, }unit tests"
else
  (cd "$repo" && python3 -I -m unittest discover -s tests "$@") || failed="${failed:+$failed, }unit tests"
fi

if [ -n "$evals" ] && [ -n "$failed" ]; then
  echo "verify: FAILED ($failed); the evals were not run"
  exit 1
fi
if [ -n "$evals" ]; then
  echo "== evals (cost ceiling \$${SDLC_EVAL_MAX_USD:-5})"
  SDLC_GATE=off claude plugin eval "$repo/plugins/sdlc" --scaffold --trust-plugin --no-publish \
    --allow-tools Bash Write Edit \
    --max-cost-usd "${SDLC_EVAL_MAX_USD:-5}" --threshold "${SDLC_EVAL_THRESHOLD:-0.8}" "$@" || failed="evals"
fi

if [ -n "$failed" ]; then
  echo "verify: FAILED ($failed)"
  exit 1
fi
echo "verify: ok"
