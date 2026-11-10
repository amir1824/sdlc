---
name: sdlc-build-to-ship-end-to-end
tags: [sdlc,e2e]
runs: 1
max_turns: 90
timeout_seconds: 840
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
/sdlc:sdlc continue the slugify feature in .sdlc/slugify from stage 5 Build. Stages 1 to 4 are done and approved (scope and plan). Carry on through the last stage the pipeline allows today and then stop. There is no CI and no deployed URL in this project. Do not commit or push.
