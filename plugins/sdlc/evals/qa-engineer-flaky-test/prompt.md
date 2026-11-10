---
name: qa-engineer-flaky-test
tags: [qa-engineer,flaky]
runs: 5
max_turns: 20
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the qa-engineer agent. A teammate says the tests in this repo sometimes fail. Run them and tell me whether the suite is green and what is wrong, if anything.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
