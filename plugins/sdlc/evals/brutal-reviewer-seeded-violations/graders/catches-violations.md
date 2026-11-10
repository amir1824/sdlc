---
type: llm
weight: 1
---
The diff seeds these violations: `any` type, console.log, switch over 3+ cases (should be a lookup map), magic number 86400, commented-out code, else block, more than 3 parameters, unused import (readFileSync). A good review names at least five of them, cites file:line for each, and ends with a Path to 10/10. A review that misses most of them, or invents problems that are not in the diff, fails.
