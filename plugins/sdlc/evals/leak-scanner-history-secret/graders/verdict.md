---
type: regex
target: last_message
pattern: 'Status:\s*\**\s*LEAKS'
match: contains
flags: i
---
A token still in git history is a leak, even though the current tree is clean.
