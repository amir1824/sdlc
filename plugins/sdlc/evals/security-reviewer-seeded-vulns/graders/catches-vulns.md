---
type: llm
weight: 1
---
The diff seeds four vulnerabilities in `src/invoices.ts`: SQL injection (the id is interpolated into the query), IDOR (the invoice is fetched by id with no check that it belongs to `req.userId`), path traversal (`req.params.file` is joined to the invoice folder without confining it, so `../../etc/passwd` escapes), and a leak of the Authorization header into logs. A good report names at least three of the four with `file:line`, gives a concrete attack input for each, and a minimal fix (parameterised query, owner check, resolve and confine the path, drop the header from the log). It fails if it misses most of them, or pads the report with generic advice not tied to this code.
