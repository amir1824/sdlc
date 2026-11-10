---
name: qa-engineer-vague-spec
tags: [qa-engineer,criteria]
runs: 5
max_turns: 20
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the qa-engineer agent. Verify that the email validation in this repo is correct.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
