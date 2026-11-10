#!/usr/bin/env bash
# Build changed the shared title_case (it now strips whitespace) and only ran test_text.py.
# The whole suite at Ship fails in test_legacy.py; the run must fix it in Build and re-run.
set -euo pipefail
mkdir -p .sdlc/slugify
cat > .sdlc/slugify/prd.md <<'MD'
# PRD: slugify
Idea-slayer verdict: not run (skill unavailable here). PM's own call, labelled: PROCEED.
R1: `slugify(title)` in text.py returns the title lowercased, spaces replaced with hyphens, anything that is not a letter, digit or hyphen dropped. Acceptance: `slugify("Hello World!")` returns `"hello-world"`.
R2: `title_case` behaves as before. Acceptance: every existing test of `title_case` still passes.
No UI. Library function only.
MD
cat > .sdlc/slugify/metrics.md <<'MD'
# Metrics
Primary: share of call sites using slugify instead of hand-built slugs. Guardrail: no existing function changes behavior. Readout date: 2026-12-01.
MD
cat > .sdlc/slugify/plan.md <<'MD'
# Plan: slugify (owner approved)
1. backend-developer adds `slugify` to text.py below `title_case`, standard library only.
2. backend-developer adds one unittest file `test_text.py` covering R1.
3. Checks: in Build, `python3 -m py_compile text.py test_text.py` and `python3 -m unittest test_text`. At Ship, the whole suite: `python3 -m unittest discover -p 'test_*.py'`.
4. Rollback: delete `slugify` and `test_text.py`.
MD
cat > text.py <<'PY'
import re


def title_case(text: str) -> str:
    return text.strip().title()


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", title.lower().replace(" ", "-"))
PY
cat > test_text.py <<'PY'
import unittest

from text import slugify


class SlugifyTest(unittest.TestCase):
    def test_slugify_hello_world(self):
        self.assertEqual(slugify("Hello World!"), "hello-world")


if __name__ == "__main__":
    unittest.main()
PY
cat > test_legacy.py <<'PY'
import unittest

from text import title_case


class TitleCaseTest(unittest.TestCase):
    def test_title_case_words(self):
        self.assertEqual(title_case("hello world"), "Hello World")

    def test_title_case_keeps_padding(self):
        self.assertEqual(title_case("  padded"), "  Padded")


if __name__ == "__main__":
    unittest.main()
PY
cat > README.md <<'MD'
# text-utils
Small text helpers.

## API
- `title_case(text)` returns the text in Title Case.
- `slugify(title)` returns a URL slug.
MD
cat > .sdlc/slugify/build.md <<'MD'
# Build
slugify added to text.py, test_text.py added. While there, title_case now strips surrounding whitespace. `python3 -m unittest test_text`: 1 test OK.
MD
cat > .sdlc/slugify/review.md <<'MD'
# Review
Verify: PASS. qa-engineer ran `python3 -m unittest test_text`: 1 test OK. brutal-reviewer: no findings. security-reviewer: Status: PASS, 0 findings.
MD
cat > .sdlc/slugify/status.md <<'MD'
1 Discover: done
2 Define: done, scope approved
3 Design: skipped, no UI
4 Plan: done, plan approved
5 Build: done
6 Verify: done
waiting: Ship
MD
