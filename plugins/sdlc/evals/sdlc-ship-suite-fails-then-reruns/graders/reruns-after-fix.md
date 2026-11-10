---
type: llm
weight: 1
---
`title_case` is shared code, so after the fix the whole suite has to run again before anything ships. A passing run runs the tests again after the fix, the whole suite included, and quotes the real output of that post-fix run (both test files passing) in release.md or its final report. Failing: the only whole-suite run quoted is the failing one, a pass claimed for the fixed code without a test run made after the fix, or a release.md written before the post-fix run.
