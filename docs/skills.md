# Skills the agents may load, and are not bundled

The six gate skills (`architecture-slayer`, `idea-slayer`, `change-impact`, `canary-watch`, `browser-qa`, `click-path-audit`) ship inside the plugin as `sdlc:<name>`; see `plugins/sdlc/skills/THIRD_PARTY_NOTICES.md`.

The skills below appear in the agents' "load when they fit" lists. They are optional: when one is not installed, the agent carries on without it. Most come from the [ECC plugin](https://github.com/affaan-m/ECC); install it to get them.

| Skill | Source | Used by |
|---|---|---|
| `anthropic-skills:built-in-browser` | Claude app skills | `frontend-developer`, `product-designer`, `qa-engineer` |
| `anthropic-skills:humanizer` | Claude app skills | `docs-engineer` |
| `ecc:accessibility` | ECC | `product-designer` |
| `ecc:api-design` | ECC | `backend-developer` |
| `ecc:architecture-decision-records` | ECC | `tech-lead` |
| `ecc:benchmark` | ECC | `refactor-engineer` |
| `ecc:coding-standards` | ECC | `refactor-engineer` |
| `ecc:competitive-report-structure` | ECC | `user-researcher` |
| `ecc:dashboard-builder` | ECC | `analyst` |
| `ecc:database-migrations` | ECC | `backend-developer` |
| `ecc:deployment-patterns` | ECC | `devops-engineer` |
| `ecc:design-system` | ECC | `product-designer` |
| `ecc:docker-patterns` | ECC | `devops-engineer` |
| `ecc:docs-governance` | ECC | `docs-engineer` |
| `ecc:e2e-testing` | ECC | `qa-engineer` |
| `ecc:error-handling` | ECC | `backend-developer` |
| `ecc:frontend-a11y` | ECC | `frontend-developer` |
| `ecc:frontend-design-direction` | ECC | `product-designer` |
| `ecc:github-ops` | ECC | `devops-engineer` |
| `ecc:i18n-sync` | ECC | `frontend-developer` |
| `ecc:living-docs-governance` | ECC | `docs-engineer` |
| `ecc:market-research` | ECC | `product-manager`, `user-researcher` |
| `ecc:plan-prd` | ECC | `product-manager` |
| `ecc:product-lens` | ECC | `analyst`, `product-manager`, `user-researcher` |
| `ecc:react-patterns` | ECC | `frontend-developer` |
| `ecc:react-performance` | ECC | `refactor-engineer` |
| `ecc:security-review` | ECC | `backend-developer` |
| `ecc:tdd-workflow` | ECC | `qa-engineer` |
| `restructure-codebase` | this repo, `extras/restructure-codebase` (not bundled; has an eval suite) | you, by hand; not yet in an agent's list |

`ecc:plan-prd` is an ECC command, not a skill folder.

The four ECC skills mention other ECC skills (`architecture-decision-records`, `contract-first`, `test-collaboration`, `module-regression`), slash commands, plugins and MCP tools that are not bundled. They are skipped when absent; the skills are copied unchanged, so those mentions stay as ECC wrote them.
