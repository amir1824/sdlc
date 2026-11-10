---
name: sdlc-ab-slugify
tags: [ab]
runs: 2
max_turns: 90
timeout_seconds: 900
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
/sdlc:sdlc add `slugify(title)` to text.py: lowercase, spaces to hyphens, drop anything that is not a letter, digit or hyphen. Add one unittest file for it. The owner pre-approves every STOP gate in this run (scope and plan): do not wait, carry through every stage the pipeline allows today, and report the result. There is no CI and nothing is deployed. Do not commit or push.
