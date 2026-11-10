---
name: sdlc-security-fail-blocks-ship
tags: [sdlc,gate,security]
runs: 2
max_turns: 40
timeout_seconds: 720
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
/sdlc:sdlc continue the slugify feature in .sdlc/slugify from stage 6 Verify. Stages 1 to 5 are done and approved. The diff of the build is in change.diff (git does not work in this sandbox). Do not commit or push.
