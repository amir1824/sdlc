---
name: security-audit-pass-needs-two-verdicts
tags: [security,gate]
runs: 2
max_turns: 25
timeout_seconds: 480
allowed_tools: [Agent, Read, Glob, Grep, Bash, Skill]
---
/sdlc:security-audit
