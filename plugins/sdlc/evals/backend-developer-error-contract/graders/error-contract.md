---
type: llm
weight: 1
---
A passing reply keeps absence and failure apart. A missing user returns None, with an Optional return type hint. An id that is not a positive integer raises an error (ValueError or TypeError) whose message names the bad input. It never returns -1, an empty string, False or any other magic value as a failure marker, and it does not swallow the error. It adds tests for all three cases (found, missing, invalid id), quotes the test command and its real output, and does not claim passing tests it did not show.
