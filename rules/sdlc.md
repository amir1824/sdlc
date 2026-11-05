# SDLC and agent workflow

Use the lightest process the risk allows. A gate is never skipped silently: a skipped gate is reported as skipped, never as passed.

## 1. Classify the risk first
Say the class in one line before the first edit. When two classes fit, take the higher; when grepping the callers shows more blast radius, raise it. The user can override the class.

| Risk | Examples | Process |
|---|---|---|
| LOW | small UI change, local refactor, docs, isolated bug fix (one module, no shared contract, undone by a revert) | Do it yourself. No plan, no review agent. Verify with the one check that proves it. |
| MEDIUM | new feature, shared component, API behavior change, multi-module change | A short plan with acceptance criteria in the reply, then implement, test, independent review. Proceed unless the plan holds a decision that is the user's. |
| HIGH | authentication or authorization, database migration, distributed system, concurrency or data integrity, infrastructure, breaking API change, anything security-sensitive | Design review before code: failure analysis, verification strategy, rollback. **The user says yes before the first edit.** |

A change that touches a HIGH item is HIGH whatever its size (a one-line auth fix is HIGH).

The class is not fixed at the start. When the work outgrows the approved plan (the diff reaches a HIGH item, or files or callers the plan did not name), say the new class in a line and ask the user again before going on; the earlier yes does not cover it.

## 2. Stages and gates
A stage's entry is the previous stage's exit; the first entry is the request. A failed exit sends the work back to the stage that owns the fix, not forward. Each cell is the exit criterion at that risk; HIGH includes everything in MEDIUM.

| Stage | LOW | MEDIUM | HIGH adds |
|---|---|---|---|
| Understand | the goal and the check that proves it, in a line | goal, constraints, numbered testable acceptance criteria; unknowns asked, never invented | what must not break; what is irreversible |
| Design | none | approach, files touched and their callers (grepped); one recommendation and the alternative rejected | contracts, trade-offs, failure modes per dependency (down, slow, wrong, duplicated, out of order), verification strategy, rollback; a must-not-happen list (outcomes the change may never produce) and the assumptions about the request, both shown to the user; `architecture-slayer` and `ecc:change-impact` run; the user's yes |
| Implement | the edit; type-check and lint clean on touched files | small reversible steps, contract first when two sides build; the test files written or changed, plus the files the project's own related-tests command selects for the touched files, are run in one foreground process (only the written or changed files when the project has no such command) | additive or behind a flag where possible; migrations reversible or flagged as not |
| Verify | the check from Understand, run, output quoted | every acceptance criterion exercised on the real behavior (a UI in the real page), plus one failure path; output quoted | failure injected (bad input, dependency down, concurrent callers); each must-not-happen line checked or listed as not covered; each run records the code it ran on (commit plus uncommitted changes; `/sdlc` has the command), so a later edit shows which runs went stale; rollback rehearsed or its dry run shown; "not shown against the real environment" said when so |
| Review | read your own diff | an agent that did not write it reviews the diff against the criteria; findings fixed or written down with a reason | `security-reviewer` too, and `qa-engineer` for user flows; after round 3 stop and reconsider the approach |
| Ship | commit only when asked | the whole suite on the release candidate (see below), recorded with the code it ran on; docs match the code; the rollback in a line | rollback steps written before shipping; a health check, log or alert that shows it broke; `devops-engineer`; `ecc:canary-watch` when a URL is deployed |
| Learn | nothing | a fix leaves the check that failed before it | what Verify or Review caught late; a recurring cause becomes a lint rule, hook, test or an edit to these rules |

The gate commands (type-check, lint, tests) are the project's own, named in its `CLAUDE.md`. **The whole suite runs at Ship, on the release candidate**: in CI, or, when CI is unavailable, locally by the orchestrator in one foreground process. Never after each edit, never from several agents at once (one child process per test file heats the machine). A subagent runs the test files it wrote or changed, plus the files the project's own related-tests command selects for its touched files (only the written or changed files when the project has none), in one foreground process and never while another agent runs tests. For HIGH work, and for MEDIUM work whose grepped callers (Design) show a shared module with many dependents, the orchestrator may also run the tests the change can affect, in one foreground process. A change after the suite ran (a fix for a failure it found included) re-runs the tests it can affect, and the whole suite again when it touched shared code: no code ships that no test run has seen.

### Planning a plugin
The plan for a plugin or mod, new or changed, includes a draw.io diagram, made with the draw.io tool (`create_diagram`, after `get_drawio_reference`). It shows the parts and how they connect: the events and hooks it listens to, the state it keeps and where, the surfaces it draws on, the files and host calls it reads and writes, and whatever runs on a timer or once per item. What is new or changed is marked. The diagram is shown with the plan the user approves. `tech-lead` has no draw.io tool, so the main session draws it from `tech-lead`'s plan.

## 3. Definition of done
- Every acceptance criterion met, with evidence: a command and its real output, or behavior observed. A successful compile or green CI alone is never done.
- Type-check and lint clean on the touched files; the suite run at Ship on the release candidate, or reported as not run.
- MEDIUM and above: reviewed by an agent that did not write the change; every finding fixed or written down with a reason.
- A way back is known: a revert for LOW, written steps for MEDIUM and above.
- Docs, changelog and types updated where behavior changed; no dead code, no debug leftovers.
- A regression check left behind for each fix.

## 4. Agent orchestration
Default to one context doing the whole task: planning, implementing and testing share context, and a subagent starts cold. Delegate only for a reason below.
- **Delegate** when: the side work is verbose and only its summary matters (wide search, log reading); a reviewer should not have seen how the code was written; two pieces have disjoint files and a written contract; a role needs tools you lack (`qa-engineer` drives the browser).
- **Do not delegate** a LOW change, iterative work, a task whose brief costs more than the work, or the same task to get a "better" answer.
- **Roles that exist:** `tech-lead` (plans, read-only; `product-designer` too for UI), `backend-developer` and `frontend-developer` (one side of a defined contract), `qa-engineer` (acceptance criteria, tests, bugs), `brutal-reviewer` (code review), `security-reviewer` (exploitable flaws), `devops-engineer` (CI, deploy, rollback), `docs-engineer`. Use these; add no agent for what one of them covers.
- **A brief carries:** the goal; numbered acceptance criteria; the files it may edit and that it touches no others; the contract with the other side; the check to run; what to return: a verdict, the commands run with their real output, and findings as `file:line`, severity, repro. Give a reviewer the diff and the criteria, not your conclusion.
- **No conflicting edits:** one writer per file. Parallel writers get disjoint file lists or their own worktree. Planners and reviewers are read-only.
- **A report is not proof.** Before saying done, read the diff or re-run the cheapest critical check yourself.
- **The user decides** the HIGH design, a change of scope, and anything hard to reverse or outward-facing: commit, push, publish, send, deploy, delete, a migration on real data, or anything the request did not ask for. Git is the user's.

## 5. Commits
One commit per finished task, only when asked. Lowercase, imperative, semantic prefix: `feat:` `fix:` `refactor:` `improve:` `chore:`
> `fix: resolve race condition in canvas rendering pipeline`

The `/sdlc` command is the heavy path for a product feature that starts from an idea (research, PRD, design, plan, build, verify, ship, launch, learn) with owner gates. It is opt-in; ordinary MEDIUM and HIGH work follows this file without it. Its Learn stage waits for the readout date in `metrics.md`, and nothing triggers it on its own: at Ship the chair writes that date in `status.md` as pending and offers the user a scheduled reminder for it; it creates the reminder only on a yes.
