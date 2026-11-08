---
type: regex
target: {source: file, path: tests/money.test.js}
match: not_contains
---
toFixed\(2\) \+ ' USD'
