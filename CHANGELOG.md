# Changelog

All notable changes, newest first. Versions follow [semver](https://semver.org): a change that alters how an agent or a gate behaves is a minor version, and a wording fix is a patch.

## 0.1.0 (2026-11-03)

First release.

- 14 role agents: tech-lead, product-manager, product-designer, analyst, user-researcher, backend-developer, frontend-developer, qa-engineer, brutal-reviewer, security-reviewer, refactor-engineer, devops-engineer, docs-engineer, leak-scanner.
- Commands: `/sdlc`, `/brutal-review`, `/security-audit`.
- 7 engineering rules and `scripts/install.sh` / `scripts/check.sh`.
- `/sdlc` additions:
  - `intent.md` for a stated problem.
  - Requirement IDs and a requirement map.
  - The plan's Instances, Contract test and Trust boundaries sections.
  - A `waiting:` / `closed` / `abandoned:` line at the end of `status.md`.
  - A lessons library rated in the retro. Agent files never change from a run.
- Launch is skipped when `/campaign` is not installed.
- On a LOW request `/sdlc` says so and recommends doing it directly; the owner decides at the first STOP gate, and no code is written before Build.
