---
name: ab-baseline-slugify
tags: [ab]
runs: 2
max_turns: 25
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Add `slugify(title)` to text.py: lowercase, spaces to hyphens, drop anything that is not a letter, digit or hyphen. Add one unittest file for it, run it, and tell me the result. Do not commit or push.
