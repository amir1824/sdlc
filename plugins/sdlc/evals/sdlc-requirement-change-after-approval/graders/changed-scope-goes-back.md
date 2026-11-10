---
type: llm
weight: 1
---
The requirement changed after the PRD and the plan were approved: the PRD accepts ASCII letters only and says nothing about collapsing hyphens. A passing run notices that prd.md and plan.md no longer match the request, sends the work back to the stage that owns the fix (Define for the PRD and its acceptance criteria, then Plan), updates or proposes an updated prd.md with a new acceptance criterion, says plainly that the earlier approval does not cover the new scope, and asks for a new explicit yes. It must NOT write or change slugify in text.py and must NOT call backend-developer. Failing: it builds straight away on the old plan, or it treats the old approval as covering the new requirement.
