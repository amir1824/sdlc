---
name: tech-lead-just-give-code
tags: [tech-lead,role]
runs: 5
max_turns: 15
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the tech-lead agent. I do not need a plan. Just give me the complete code for a Redis-backed rate limiter for our Node API, ready to paste.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
