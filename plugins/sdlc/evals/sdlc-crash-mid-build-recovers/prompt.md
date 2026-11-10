---
name: sdlc-crash-mid-build-recovers
tags: [sdlc,recovery]
runs: 2
max_turns: 40
timeout_seconds: 720
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
/sdlc:sdlc continue the slugify feature in .sdlc/slugify. The previous run crashed in the middle of stage 5 Build and I do not remember what was finished. Do not commit or push.
