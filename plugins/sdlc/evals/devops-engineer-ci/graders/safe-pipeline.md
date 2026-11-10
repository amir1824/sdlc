---
type: llm
weight: 1
---
The reply shows the workflow YAML (or clearly describes it) and the file path under .github/workflows. A passing pipeline: runs CI on pull_request; uses `npm ci`; caches dependencies; sets least-privilege `permissions` (read-only by default); takes the deploy token from `secrets.*` and never inline; runs the deploy only for tags; pins actions to a version (a major tag such as v4 is acceptable). It also states a rollback or release plan and flags assumptions about the deploy target. Missing one or two minor items is acceptable if the secret handling, tag gating and PR trigger are right.
