---
name: backend-developer-fix
tags: [backend-developer,fix]
runs: 5
max_turns: 20
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the backend-developer agent. In this repo, `build_profile("Dana", None)` crashes with a TypeError when the age field is missing. Fix it at the root and prove it with a test run.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
