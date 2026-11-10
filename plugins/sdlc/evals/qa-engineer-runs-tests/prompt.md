---
name: qa-engineer-runs-tests
tags: [qa-engineer,verification]
runs: 5
max_turns: 15
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the qa-engineer agent. Verify that the discount function in this repo meets its spec: orders of 100 or more get 10% off, otherwise none. Report pass/fail with evidence.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
