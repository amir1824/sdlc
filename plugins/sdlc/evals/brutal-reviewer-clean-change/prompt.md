---
name: brutal-reviewer-clean-change
tags: [brutal-reviewer,review,negative]
runs: 5
max_turns: 15
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the brutal-reviewer agent to review the current changes in this repo and return its review as-is.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
