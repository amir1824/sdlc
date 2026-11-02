---
description: Run the security department, security-reviewer on the diff and leak-scanner on the whole repo, and merge their findings into one report
argument-hint: [diff | release | files or focus area]
---

Run a security audit of this repo.

Scope: $ARGUMENTS

- `diff`: run only the security-reviewer agent on the current changes.
- `release`: run only the leak-scanner agent on the whole repo and its history.
- Empty, or anything else: run both agents in parallel, and pass the scope to security-reviewer as its focus.

Then merge their reports into one:

1. One status line: `Status: BLOCK` if either agent reported BLOCK or LEAKS, otherwise `Status: PASS`.
2. Findings from both, sorted Critical, High, Medium, Low. When both found the same `file:line`, keep one and note that both agents found it.
3. Each agent's Scanners and Not covered sections, as-is.

Do not soften findings or drop the Low ones. Never print a full secret value.
