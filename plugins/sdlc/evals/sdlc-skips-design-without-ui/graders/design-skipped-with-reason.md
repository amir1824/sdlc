---
type: llm
weight: 1
---
The PRD says there is no UI. A passing run does not run the product-designer for stage 3. It records stage 3 Design as skipped, with the reason (no UI), in `.sdlc/slugify/status.md` or in its reply, and it says the skip out loud. Failing: it writes a `design-spec.md`, it calls the product-designer, or it skips stage 3 without writing a reason.
