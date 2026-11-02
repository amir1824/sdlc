---
description: Run the brutal-reviewer agent on the current diff (or on the files/focus you name)
argument-hint: [files or focus area]
---

Use the brutal-reviewer agent to review the current changes.

Scope: $ARGUMENTS

If the scope above is empty, review the working-tree `git diff` (fall back to `git diff --staged`, then to the last commit). Return the agent's findings and score as-is, without softening them.
