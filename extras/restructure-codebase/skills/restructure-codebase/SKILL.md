---
name: restructure-codebase
description: Restructure a whole codebase (or a large area of it) so each fact has one definition and each module depends only on things that change less, then prove the behaviour did not change. Use only when the user asks to untangle, restructure or clean up the codebase as a whole; not for a single bug, feature or file.
argument-hint: "[area or concern to focus on]"
---

Restructure this codebase and finish the job. A good result is one where a typical change lands in one place, and the program does what it did before, except for bugs you fixed and changes the owner approved.

## Rules that hold the whole way

1. **Behaviour is the contract.** Every change you make must keep what a user, caller or other service can observe: responses, error messages, defaults, events, stored data, UI states. A change that does not is a *behaviour change*. Write each one in `restructure-log.md` the moment you make it, with its kind (`bug fix` or `owner approved`) and the evidence. If it is neither, undo it.
2. **Fix bugs; ask only about intent.** A bug is behaviour the code itself contradicts: a copy of a list that disagrees with its source, a skipped test that states the expected result, a call order only some callers follow, a crash on a path the code already offers. Fix it unless the owner said not to, and log it as a `bug fix` with that evidence. Untangling usually exposes these, so keeping one in place to "preserve behaviour" is a miss. Ask the owner only when the change is to behaviour that looks intended (removing a public route, tightening a permission, changing a default): one batch of questions, then carry on. Park what stays undecided in the log under *Deferred*.
3. **Never fix by deleting evidence.** A failing test is a finding. Do not skip, loosen or quarantine it to get green.

## 0. Freeze the starting point

- Note the starting commit and keep it reachable (`git tag restructure-base` or write the SHA in the log).
- Run every gate the project has (types, lint, tests, boundary checks) and record what passes. A gate that already fails is listed, not fixed on the way.
- For each area you will touch with no test around its observable behaviour, write a small characterization test first: it asserts what the code does today, quirks included. Those tests are your safety net for step 4.

## 1. Ask which extras to do

Offer these two, with their exact wording, and do only what is chosen. If the user already stated their choice, use it and do not ask again.

| Extra | What it does |
|---|---|
| **Comments** | Remove comments that only say what the next line says. Keep comments about things outside the code (a proxy, a vendor, a rule, a deadline) and `TODO`s that still describe a real gap. |
| **Tests** | Remove tests that would pass for any implementation or only repeat the code under test; rewrite tests tied to internals so they assert behaviour. Never remove the only test of a real behaviour. |

## 2. List every problem before changing anything

Walk the code with one question: **do these pieces change together?** Record each wrong answer as `path:line  problem`.

- **Together, but nothing shows it:** copies of a rule or value; one module reading state another one sets; a feature spread over layers; a call order every caller must know; two lists of the same things (a menu and a palette, a switch and a table).
- **Tied, but change for different reasons:** callers using a module's internals; stable code importing volatile code; a general function with a parameter only one caller understands; a module that is as complicated to use as to write.
- **No reason to exist:** pass-through wrappers; options and extension points nothing varies; dead code; re-exports nobody imports.
- **Special cases:** an `if` for one value, a parameter for one caller, a swallowed error, a retry or sleep, a disabled test. Each one is a requirement the design never named. Find out which are still real (keep them, and make them explicit) and which only patch another problem (the redesign removes them).

Use cheap tools to see the whole: a script that prints the import graph; a skeleton view of the signatures; `git log` to see which files change together; subagents to summarise one area each.

## 3. Redesign

Group the problems by the **one fix** behind several of them; it rarely looks like any of them. Write the fix above its problems in the log. Judge each fix by three questions: do things that change together now live together, are things that do not change together untied, does everything depend on what changes less? Do not add an abstraction for its own sake: most fixes delete, merge, derive from one definition, or move.

## 4. Fix, in waves

- Work area by area. After each wave run all the gates, then the characterization tests, then look at the diff of observable behaviour (routes, schemas, messages, labels, queue payloads, env names and defaults). Merge the next wave only when the last one is clean.
- If subagents work in parallel, give each its own area and its own worktree, and have them report behaviour changes in the log format. Re-check the base of each worktree before it starts.
- With *Comments* chosen, remove restating comments last in each area. With *Tests* chosen, do the test work last of all, because the tests are the safety net until then.
- Keep the diff reviewable: if it reaches hundreds of files, say so, and split it by area into commits or pull requests that each stand alone.

## 5. Check, and repeat

Run both checks, then fix what they find and run them again:

1. **Structure.** Subagents search for the four kinds of problem from step 2 in what is left.
2. **Behaviour.** One subagent per area compares the base commit with now, and reports every observable difference. It reads code and runs the app or the tests; it does not look for style. Each difference is either already in the log, a bug fix you can show, or something to undo or ask the owner about.

You are done when no worthwhile structural problem is left, the behaviour audit finds nothing outside the log, every gate that passed at the start passes now, and the count of special cases went down. Say so with numbers, not adjectives.

## 6. Report

Finish with: files and lines changed; the problems fixed, grouped by fix; the *Behaviour changes* table (kind, what, evidence); the *Deferred* list with what each needs from the owner; and which gates ran, which did not and why.

## Log format

```md
## Fixes
- One `Dialog` returns focus to what had it before; the 100ms wait and the `skipRefocus` flag go.
  - ui/LogoutDialog.tsx:30  waits 100ms after closing and hopes focus has landed
  - ui/SettingsDialog.tsx:61  sets a global flag to stop that focus change
## Behaviour changes
- bug fix: saving a link no longer drops its `kind` (history/link.ts:44; test added)
## Deferred
- Remove `POST /chat/execute`? Needs the owner: a public route
```
