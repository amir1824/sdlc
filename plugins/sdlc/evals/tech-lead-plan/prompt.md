---
name: tech-lead-plan
tags: [tech-lead,planning]
runs: 5
max_turns: 15
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the tech-lead agent. We run a small TypeScript web app (React front end, Node API, Postgres). Plan how to add per-user API rate limiting with a visible "slow down" message in the UI. Do not write the implementation.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
