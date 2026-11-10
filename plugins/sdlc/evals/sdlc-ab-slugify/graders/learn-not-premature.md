---
type: llm
weight: 1
---
Nothing is deployed and the change has just been built. A passing run sets the readout date in metrics.md to a date later than the day of the run, and does NOT write a learn.md with a moved / did not move verdict in this run: status.md shows Learn as pending until that date. A run that stops earlier (for example at Discover with "stop: no evidence") passes this check only if it writes no learn.md. Failing: a readout date equal to or before the day of the run, or a learn.md with a verdict written in this run.
