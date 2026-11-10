---
name: tech-lead-tradeoff
tags: [tech-lead,decision]
runs: 5
max_turns: 15
timeout_seconds: 420
allowed_tools: [Agent, Read, Glob, Grep, Bash, Write, Edit, Skill]
---
Use the tech-lead agent. We are one developer on one small VPS, with Postgres already running. Every night we must email a summary report to about 200 users, and we want it reliable and cheap to run. Option A: a Kafka-based pipeline with consumers. Option B: a scheduled job (cron) that reads from Postgres and sends the emails. Decide.

Return the sub-agent's complete output verbatim as your final message. Do not summarize, shorten or comment on it.
