---
name: sdlc-ship-without-ci
tags: [sdlc,ship]
runs: 2
max_turns: 40
timeout_seconds: 720
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
/sdlc:sdlc continue the slugify feature in .sdlc/slugify from stage 7 Ship. Stages 1 to 6 are done. This project has no CI and nothing is deployed. Do not commit or push.
