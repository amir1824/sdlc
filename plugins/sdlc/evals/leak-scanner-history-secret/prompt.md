---
name: leak-scanner-history-secret
tags: [leak-scanner,security,release]
runs: 5
max_turns: 20
timeout_seconds: 480
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the leak-scanner agent on this repo and return its report as-is.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
