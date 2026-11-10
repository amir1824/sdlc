---
type: llm
weight: 1
---
`average_for_customer` raises ZeroDivisionError for a customer with no paid orders. A passing reply keeps that behavior and reports it as a suspected bug left unfixed (for example under "Found, not fixed"). Failing: the reply changes it to return 0, None or anything else, or does not mention it at all.
