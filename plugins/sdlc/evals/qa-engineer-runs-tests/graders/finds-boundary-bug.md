---
type: llm
weight: 1
---
The code uses `total > 100` but the spec says 100 or more is discounted, and the existing tests (inputs 50 and 200) never hit the boundary. A passing reply gives a verdict of FAIL, says that `discount(100)` returns 100 where 90 is expected, points at the `>` comparison as the cause, includes the command it ran with its output, and recommends a test at exactly 100. A reply that says everything passes, or never identifies the exact-100 case, fails.
