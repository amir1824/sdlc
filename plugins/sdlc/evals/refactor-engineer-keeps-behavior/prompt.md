---
name: refactor-engineer-keeps-behavior
tags: [refactor-engineer,behavior]
runs: 5
max_turns: 30
timeout_seconds: 600
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the refactor-engineer agent. Improve orders.py: less code, clearer and faster, with the same behavior.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
