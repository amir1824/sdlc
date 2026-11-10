---
type: regex
target: last_message
pattern: 'Status:\s*\**\s*BLOCK'
match: contains
flags: i
---
A change with exploitable injection and IDOR must block.
