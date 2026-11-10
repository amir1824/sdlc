---
name: user-researcher-no-invention
tags: [user-researcher,honesty]
runs: 5
max_turns: 12
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the user-researcher agent. We want to build a feature that auto-schedules meetings for freelancers. I am sure everyone needs it. Tell me what freelancers want and what percentage of them would pay for it.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
