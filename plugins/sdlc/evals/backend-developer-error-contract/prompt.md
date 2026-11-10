---
name: backend-developer-error-contract
tags: [backend-developer,errors]
runs: 5
max_turns: 20
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the backend-developer agent. Add `get_user_email(user_id)` to users.py, next to `get_user_name`. A user who does not exist is a normal case, not an error. An id that is not a positive integer is a bug in the caller. Add tests and run them. In your report, show the final code of the new function.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
