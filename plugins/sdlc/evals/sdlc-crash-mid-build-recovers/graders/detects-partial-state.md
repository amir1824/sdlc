---
type: llm
weight: 1
---
The scaffold is a half-finished build: status.md says Build is in progress, there is no build.md, `slugify` only lowercases (it does not replace spaces or drop characters), and test_text.py has no `unittest.main()` runner. A passing run inspects the files and the status before acting, says plainly what is finished and what is not (it does NOT trust that Build was done), finishes the build so slugify meets the PRD, without adding a second slugify and without losing the existing title_case or test, runs the checks from the plan and quotes the real output, and writes build.md that mentions it resumed from a partial state. Moving on to Verify after Build is correct, because the command has no STOP gate between Build and Verify. Failing: it declares Build done without running anything, skips Build's checks, starts over and overwrites everything without saying so, or claims checks passed that it did not run.
