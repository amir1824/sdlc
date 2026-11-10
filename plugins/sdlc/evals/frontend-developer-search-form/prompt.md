---
name: frontend-developer-search-form
tags: [frontend-developer,a11y]
runs: 5
max_turns: 15
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the frontend-developer agent. Write a React + TypeScript SearchBox component in SearchBox.tsx: a controlled input with a submit button, a loading state and an error state. The app ships in Hebrew (RTL) and English.

Return the sub-agent's complete output verbatim as your final message, and also paste the full contents of SearchBox.tsx in a code block at the end. Do not summarize, shorten or comment on it.
