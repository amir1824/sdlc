# Architecture & state

## Boundaries and contracts
- **Parse at the boundary, trust afterwards.** The `api/` layer validates responses once and returns a type. Nothing downstream re-checks shape, and nobody hand-types a response object.
- **Context boundaries are real.** `features/<context>/*` does not import from another context. Shared dependencies move to `shared/`. `shared/` never imports `features/` (ESLint-enforced; the app-shell layout components are the only allowlisted exceptions).
- **Contracts first.** When two sides are built in parallel, the interface between them (API shape, event name, type) is written before either starts. Change a contract additively, and list its consumers first.
- **Pin versions** of dependencies, images and actions so builds are reproducible.

## Anti-patterns (never do)
- ❌ "God" objects, giant hooks, or files spanning unrelated domains.
- ❌ Modifying a shared component to serve one caller's edge case — pass a slot, or keep it local.
- ❌ Generic `utils/` or `helpers/` dumps — name files by domain purpose.
- ❌ A flat folder of many files, or sibling files sharing a topic prefix (`report_cost.py`, `report_flags.py`, `report_tables.py`). **Folders by topic first, files inside.** The third file with the same prefix, or the 9th file in a folder, is the trigger: create the topic folder in that same commit (`report/cost.py`, `report/flags.py`), and name files without the folder's prefix. Plan the folder layout before creating files, not after the user asks. Check: `ls <dir> | sed 's/_.*//' | sort | uniq -c | awk '$1>=3'` prints nothing, and `find <dir> -maxdepth 1 -name '*.py' ! -name '__init__.py' | wc -l` is ≤ 8. Exempt: `test_*` files in a `tests/` folder (pytest convention); count only source files there.
- ❌ Barrel `index` files that only re-export. Import the path directly.

## Limit
| Target | Limit | Action on violation |
|---|---|---|
| Source files per folder (direct children, excluding `__init__.py`) | ≤ 8 | Group by topic into subfolders named for the domain. |

Limits are thresholds for a second look. Over one, split it or say in a line why it stays whole.
