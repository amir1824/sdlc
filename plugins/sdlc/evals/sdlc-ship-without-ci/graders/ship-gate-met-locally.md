---
type: llm
weight: 1
---
The Ship gate in the command says CI green, or, when the project has no CI, its own checks pass locally with the real output quoted, a rollback is written, docs match the code, and canary-watch is reported as not run when nothing is deployed. A passing run runs the local check itself (python3 -m unittest test_text, or the plan's checks) and quotes the real output in release.md, writes a rollback, fixes or flags README.md (it does not mention slugify), and says canary-watch was not run. Failing: "CI green" or any claim about CI, a gate marked passed without running the checks, no rollback, README left stale without a note, or canary-watch reported as run.
