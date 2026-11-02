---
paths:
  - "**/*.{ts,tsx,js,jsx,mjs,cjs,py,go,rs,java,kt,swift,rb,php,cs}"
---

# Code standards

## Naming
- **Intention-revealing:** The name says why it exists and how it's used. No single letters (`elapsedTimeInDays`, not `d`).
- **One verb per concept, codebase-wide.** Pick `get` and never mix in `fetch` / `retrieve` / `load` for the same operation.
- **No disinformation:** Don't call something a `List` unless it is one; don't call something a `Map` that's an array.

## Functions & structural design
- **Command-Query Separation:** A function either changes state or returns data. Never both.
- **Guard clauses:** Validate and bail at the top. Early return or throw — avoid deep nesting, and prefer a guard clause to `else` (`no-else-return` is in ESLint); keep an `else` where a guard clause would read worse.
- **Prefer `map` / `filter` / `reduce` to index loops.** `for...of`, `while` and index loops are fine for polling, retries, parsing, a body that `await`s or needs an early `break`, and hot paths.
- **Pure by default:** Deterministic, inputs-only, zero side effects. Side effects get pushed to the edges where they're testable.
- **Dispatch over branching (5+ cases, or when new keys are expected):** Routing over a set of keys — event types, statuses, provider names — uses a lookup map to a strategy, not an `if/else` or `switch` chain. This keeps it O(1) and open/closed. Below that, a plain `if`, or a `switch` over a closed enum that the compiler checks for exhaustiveness, is simpler and wins.

## Error handling
- **Separate absence from failure.** Expected absence (no match, empty result) returns `undefined` or an empty structure, typed explicitly — `T | undefined` is a legitimate contract in strict TS. Operational failure (network, auth, invalid input) throws a contextualized `Error`. Never return `null`, `-1`, `false`, or a magic string as a failure marker.
- **No `null` as a parameter or as an internal failure marker.** It forces defensive branching inside the callee. If a parameter is genuinely discrete, split the function. Where `null` is the contract (DOM, JSON, SQL, third-party APIs), accept it at the boundary and convert it to `undefined` or a typed value on entry.
- **Errors carry context.** `throw new Error('...')` names what failed and with what input, not just that something failed.

## Anti-patterns (never do)
- ❌ `any` — under any circumstance. (ESLint: `no-explicit-any`.)
- ❌ `console.log` in production-bound code.
- ❌ Commented-out code blocks.
- ❌ Magic numbers and hardcoded strings — extract to a named constant.
- ❌ Comments explaining *what* the code does; rewrite the code instead. Comments explain *why* an unusual decision was made.

## Complexity limits
Limits are thresholds for a second look. Over one, split it or say in a line why it stays whole; a lint limit may be disabled on a single line with that reason.

| Target | Limit | Action on violation |
|---|---|---|
| Function parameters | ≤ 3 | Group into a typed config object. |
| Interface properties | ≤ 10 | Extract nested interfaces via extension. |
| Lines per function | ≤ 30 | Extract block operations into sub-functions. |
| Lines per file | ≤ 200 | Split into domain sub-modules. |

**Exemptions:** `*.test.ts(x)` → 400 lines (declarative tests are verbose by design, see quality-and-testing). Thin re-export wrappers over a UI primitive library (e.g. Radix in `shared/ui/`) are exempt from the file and prop limits.
Component, hook and `useState`/`useEffect` limits are in `frontend.md`; the files-per-folder limit is in `architecture-and-state.md`.
