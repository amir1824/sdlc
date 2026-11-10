---
name: lesson-l1-without
tags: [lesson, ab]
runs: 3
max_turns: 20
timeout_seconds: 600
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
This repo is at the Build stage of an /sdlc run, and the owner approved `.sdlc/currency/plan.md`. Use the backend-developer agent to do build task B1 of that plan. Brief it with the plan's path and the task ID, and nothing else.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it, and do not edit any file yourself.
