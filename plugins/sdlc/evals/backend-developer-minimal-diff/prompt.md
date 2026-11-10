---
name: backend-developer-minimal-diff
tags: [backend-developer,scope]
runs: 5
max_turns: 20
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the backend-developer agent. In this repo `paginate(items, page, size)` is wrong: pages are meant to be 1-based, so `paginate(list(range(10)), 1, 3)` must return `[0, 1, 2]` but it returns `[3, 4, 5]`. Fix it and add a regression test.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
