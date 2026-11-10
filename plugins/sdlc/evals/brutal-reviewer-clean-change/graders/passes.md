---
type: regex
target: last_message
pattern: 'Status:\s*\**\s*PASS'
match: contains
flags: i
---
A trivial, clean, reuse-based one-liner should pass; the reviewer must not invent findings.
