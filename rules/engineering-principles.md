# Engineering principles

## Core
- **The laziness ladder.** Before writing code, climb it in order: does it need to exist → does it already exist in this codebase (reuse it) → does the standard library cover it → does a native/platform feature cover it → does an installed dependency cover it → can it be one line → only then write the minimum code that works.
- **SRP:** One reason to change per function, component, or file. A module that both fetches data and renders UI gets split.
- **DRY, on the second occurrence.** A pattern appearing twice is a candidate; three times is an obligation. Don't abstract the first one.
- **KISS / YAGNI:** No abstraction for a use-case that hasn't arrived. Code is read far more often than written.
- **No Dead Code:** Unused functions, variables, imports, and old pathways are deleted in the same commit, not kept "for reference." Git remembers.
- **Root Cause Over Symptom:** A bug report names a symptom. Before patching, grep every caller of the function you're touching and fix the shared function once — a sibling caller left broken by a patch scoped to the reported path is the next bug ticket.
- **Think Downstream:** Before changing shared code, list its existing usages. Evaluate side effects, performance regressions, and breaking changes to APIs and shared types.
- **No Assumptions:** Ambiguous spec → stop and ask. Do not invent the requirement.

## Deliberate simplifications
**The `ponytail:` marker.** When a simplification cuts a real corner with a known ceiling (a global lock, an O(n²) scan, a naive heuristic), mark it with a `ponytail:` comment naming the ceiling and the upgrade path. This is the one exception to the no-what-comments rule (code-standards) — it documents a boundary, not the code.

## What laziness does not cut
Lazy means efficient, not careless. However far up the ladder a solution sits, never skimp on:
- Input validation at trust boundaries (parse at the boundary, architecture-and-state).
- Error handling that prevents data loss.
- Security and accessibility.
- Calibration against real platform quirks — the platform is never the spec ideal (a clock drifts, a sensor reads off).
- Anything the user explicitly asked for.
