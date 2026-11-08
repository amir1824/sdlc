---
type: llm
focus: trace
---
After the change, supporting a third payment provider would mean adding one new module for that provider and registering it in one place. Charging and refunding no longer need an `if` or `switch` on a provider name in more than one file. Judge from the edits shown in the transcript.
