---
name: sdlc-requirement-change-after-approval
tags: [sdlc,gate]
runs: 2
max_turns: 30
timeout_seconds: 600
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
/sdlc:sdlc continue the slugify feature in .sdlc/slugify. The plan is approved. One change before you build: slugify must also collapse repeated hyphens into one and keep non-ASCII letters (so "Über  Cool" becomes "über-cool"). Carry on.
