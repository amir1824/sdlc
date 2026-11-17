#!/usr/bin/env bash
set -euo pipefail
cat > text.py <<'PY'
def title_case(text: str) -> str:
    return text.title()
PY
mkdir -p .sdlc/slugify
cat > .sdlc/slugify/research.md <<'MD'
# Research
Problem: callers build URL slugs by hand. First audience: the developers of this small library. Riskiest assumption: nobody else already needs a different slug rule.
MD
cat > .sdlc/slugify/prd.md <<'MD'
# PRD: slugify
Idea-slayer verdict: PROCEED.
Requirement 1: `slugify(title)` in text.py returns the title lowercased, spaces replaced with hyphens, anything that is not a letter, digit or hyphen dropped.
Acceptance criterion 1: `slugify("Hello World!")` returns `"hello-world"`.
There is no UI. Library function only.
MD
cat > .sdlc/slugify/metrics.md <<'MD'
# Metrics
Primary: share of call sites using slugify instead of hand-built slugs. Guardrail: no existing function changes behavior. Readout date: 2026-12-01.
MD
{
  cat <<'MD'
run: slugify
risk: MEDIUM
path: full
base: 4b825dc642cb6eb9a060e54bf8d69288fbee4904
1 Discover: done
2 Define: done
MD
} > .sdlc/slugify/status.md
