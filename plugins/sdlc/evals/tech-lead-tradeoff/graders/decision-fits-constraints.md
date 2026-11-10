---
type: llm
weight: 1
---
A passing reply makes ONE recommendation and it fits the stated constraints (one developer, one small VPS, Postgres already there, about 200 emails a night): the scheduled job with Postgres. It names the rejected alternative (Kafka) and gives the reason tied to those constraints, not a generic one. It orders the risks by blast radius (for example duplicate or missing emails, a silent job failure) with a mitigation each, includes a definition of done, and labels anything it assumed. Failing: recommending Kafka, hedging with no decision, or a reason that ignores the constraints.
