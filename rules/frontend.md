---
paths:
  - "**/*.{tsx,jsx}"
---

# Frontend (React web apps)

Applies to React web apps. Where a project's own `CLAUDE.md` says the project is something else (for example a Claude Code mod), that file wins.

## State & data flow
- **Server state lives in TanStack Query. Only there.** ❌ `useState` holding a copy of `query.data`; ❌ `useEffect` syncing them. A local edit is an explicitly named draft (`draftTitle`), never a shadow copy of server truth.
- **One status, not boolean soup.** ❌ juggling `isLoading` + `isError` + `data` at the call site. Derive a single state and render off it.
- **No user-facing string literals in components.** All visible text goes through `useTranslation`. A new key lands in every locale file in the same commit; when a locale is right-to-left, check the layout in it.

## Anti-pattern
- ❌ Prop drilling 3+ levels. Reach for **composition first** (`children` / slots); Context only when the value is consumed by 3+ unrelated leaves.

## Complexity limits
These are review prompts, not violations: a form or a flat data shape may exceed one. Over one, look again and say in a line why it stays whole. A `useEffect` is a last resort; extract it to a dedicated hook or an event handler when it grows.

| Target | Limit | Action on violation |
|---|---|---|
| Component props | ≤ 7 | Decompose or use `children` composition. (`...rest` passthrough not counted.) |
| Hook return values | ≤ 5 | Split the hook, or return one structured object. |
| `useState` per component | ≤ 4 | Consolidate into one state object or `useReducer`. |
| Dependency array items | ≤ 5 | Extract independent state concerns. |

Thin re-export wrappers over a UI primitive library (e.g. Radix in `shared/ui/`) are exempt from the prop limit.
