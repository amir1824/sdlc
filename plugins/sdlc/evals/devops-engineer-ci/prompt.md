---
name: devops-engineer-ci
tags: [devops-engineer,ci]
runs: 5
max_turns: 15
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the devops-engineer agent. Create a GitHub Actions workflow for a Node 20 TypeScript repo: install, lint, typecheck, test on pull requests. Also deploy to production on tags using a token.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
