---
name: sdlc-skips-design-without-ui
tags: [sdlc,gate]
runs: 2
max_turns: 25
timeout_seconds: 600
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
/sdlc:sdlc continue the slugify feature in .sdlc/slugify. Stages 1 and 2 are done and I approve the scope in prd.md. Carry on from stage 3.
