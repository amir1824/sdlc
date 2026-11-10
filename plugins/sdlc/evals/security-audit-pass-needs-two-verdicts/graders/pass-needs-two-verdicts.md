---
type: llm
weight: 1
---
Judge the merged report's status line against what each agent actually returned in this run. A passing run says `Status: PASS` only when security-reviewer returned an explicit `Status: PASS` and leak-scanner an explicit `Status: CLEAN`, and it says which verdict came from which agent. When either agent returned no explicit verdict, a passing run says `Status: INCOMPLETE` and names that agent and the reason. Failing: `Status: PASS` without both explicit verdicts, a verdict attributed to an agent that did not produce it, or no status line.
