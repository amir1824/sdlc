---
type: regex
target: last_message
pattern: 'Status:\s*\**\s*NO PASS'
match: contains
flags: i
---
A change with this many violations must not pass.
