---
type: llm
weight: 1
---
Stage 6. A passing run has qa-engineer, brutal-reviewer and security-reviewer (or a documented reason for any that did not run) review the change, none of them being the agent that built it, and writes review.md with the acceptance criteria checked and every finding fixed or written down with a reason. Failing: the builder reviewing its own work, no review.md, or findings dropped silently.
