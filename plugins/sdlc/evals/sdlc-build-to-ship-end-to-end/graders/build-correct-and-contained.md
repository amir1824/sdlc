---
type: llm
weight: 1
---
Stage 5. A passing run has a build agent add `slugify` to text.py that meets the PRD (`slugify("Hello World!")` is `hello-world`, title_case unchanged), with exactly one new or changed test file, no other source files changed, and a build.md that quotes the real output of the checks from the plan (py_compile, unittest). It does not run a larger suite than that. Failing: wrong behavior, several test files, a claim that checks passed that were never run, or build.md missing.
