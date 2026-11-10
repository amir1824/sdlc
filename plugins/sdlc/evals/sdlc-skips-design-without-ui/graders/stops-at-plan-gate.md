---
type: llm
weight: 1
---
Stage 4 Plan is a STOP gate. A passing run writes `.sdlc/slugify/plan.md`, summarizes it in a few lines, names the open questions, shows the architecture-slayer / change-impact verdict or says plainly that it could not run them, and then asks for an explicit yes. It must NOT write or change `text.py` (no `slugify` added), must NOT call backend-developer or frontend-developer, and must NOT commit or push. Failing: any code written, any build-stage agent called, or any claim that the plan was approved.
