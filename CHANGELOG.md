# Changelog

All notable changes, newest first. Versions follow [semver](https://semver.org): a change that alters how an agent or a gate behaves is a minor version, and a wording fix is a patch.

## Unreleased

Gaps found by a red-team review of the process: what the plan never asked, and tests that no longer match the code.

- HIGH plans carry **Must not happen** (at least three outcomes the change may never produce) and **Assumptions about the request**, both shown at the Plan gate. `qa-engineer` gives each line its own check or lists it as `not covered`; Verify does not pass a HIGH run with a line neither checked nor accepted by the owner.
- `review.md` gets a **Test runs** table (HIGH: every run; MEDIUM: the whole-suite run at Ship): command, exit code, fingerprint of the code it ran on, time, output and the requirements it covers. The agent that ran the tests takes the fingerprint before and after; the row counts only when they are equal. At Ship, and on `/sdlc resume` after Verify, a row whose fingerprint differs from the code now is stale and runs again. This is the chair's own check, not a hook, and it shows the evidence matches the code, not that the code is right.
- An owner who accepts a `not covered` Must-not-happen line does so in their own words, quoted in `status.md`.
- Process fixes from a small experiment (7 micro tasks; plain Claude, plain Claude plus one review pass, and `/sdlc`; one run each for the last two; the hidden tests were written by the experimenter, and the owner facts given to `/sdlc` leaked what two checks scored, so it is three single runs with no variance, not a benchmark). On the three tasks where both ran, a plain run plus one review pass scored the same or better than `/sdlc` on the hidden checks (+$0.4 to +$0.5 against +$4.8 to +$7.2 per task). These fixes came from those tasks and were not re-run, so their effect is not measured. A rule that stopped a LOW request before any work until the owner replied `run it anyway` was tried and reverted: it lowered the mean eval score from 0.69 to 0.52 on 16 cases (two runs each), because the suite's small tasks stopped before the stages they test, and whoever types `/sdlc` has already chosen the pipeline; the owner still chooses at the Define STOP. `/sdlc` changes: a default that leaves a sibling, a batch variant or another reader of the same data unprotected is an **Owner question** (listed in `prd.md`, asked at the Define STOP, answered in the owner's own words), never an assumed default; the plan is sized to the change and a required section is never cut to fit; tests cover each requirement, Must-not-happen line, Instances place and failure path and nothing else; an over-build finding is fixed or kept with a reason; after the third return from Verify to Build the chair stops and tells the owner; `status.md` stage lines are rewritten in place; a denied command is reported as denied and not re-run through a wrapper. README: `/sdlc` is for multi-file features, and `claude -p` needs `--resume` per gate and the stages' commands allowed.
- Review rounds are bounded, from one demo run (not kept in the repo) in which the chair's own turns used about 90% of the cache reads; cache reads are the cheapest tokens, so this is not a cost share. The Plan stage has at most two send-backs; `security-reviewer`'s plan read tags each missing defence `[blocking]` or `[note]`; a `[blocking]` item still open goes to the owner, who accepts it in their own words. A `[note]` is built only when it answers a **Must not happen** line or a requirement, otherwise it goes to **Open findings**, and the STOP summary says whether `security-reviewer` read the whole final plan. In Verify the commands run before the reviewers, and after a non-security fix only the reviewer who raised the finding reads the changed lines. These are prompt rules, not a hook, and their effect on cost is not yet measured.
- README: the gates are described as guardrails that do not prove the requirements are right; an action that must never happen belongs in the host's permission deny rules or a sandbox.
- The plan gets an **Architecture** section. When a change adds a schema or migration, changes an event name or payload or a public API signature, or adds a dependency, a service, a trust boundary or a module (and for new-product work and HIGH work that crosses components), `tech-lead` writes As-Is and To-Be Mermaid diagrams inside `plan.md`, a component and contract table whose rows each name a check that can run, and the failure scenarios. A skip line does not satisfy a trigger, and the chair reconciles the To-Be diagram with the trust boundaries `security-reviewer` names. Otherwise it writes `Architecture diagram: skipped — <specific reason>`. The plan hash already covers the diagrams, and the chair renders them at the Plan STOP when a Mermaid-capable tool is available, otherwise it shows the source and says it is unrendered; the hash binds the file, not the owner's reading of it. The chair also checks the plan's `sdlc-scope` patterns against a short list (migrations, SQL, dependency manifests, API schemas, event definitions), so a skip line cannot hide a trigger in an obvious scope pattern; a broad pattern such as `src/**` is not caught. This is a prompt, not enforcement, and a diagram shows the proposed design, not that it is right.
- The six skills the gates call now ship in `plugins/sdlc/skills/`: `architecture-slayer`, `idea-slayer`, `change-impact`, `canary-watch`, `browser-qa` and `click-path-audit`. Before, a fresh install had none of them and every gate that needed one said "not run". The agents name them `sdlc:<name>`, and the two owner skills have no Hebrew text (trigger phrases and language notes are English); the four from ECC are copied unchanged, with the license and credits in `THIRD_PARTY_NOTICES.md`. The optional skills the agents may load are listed, not bundled, in `docs/skills.md`. Skills ship with the plugin install only; a `--link --agents` install does not link them.
- Only `approve plan` unlocks the gate. The Hebrew approval phrase is no longer accepted, so the repository has no Hebrew text. The chair still understands a clear yes in any language and answers it by asking for `approve plan`; the gate itself never interprets a reply.
- Docs: the README is shorter and simpler (172 to 115 lines). The lessons library guide moved to `docs/lessons-library.md`, unchanged. The architecture diagram is redrawn in English and matches 0.4.0 (it showed 0.2.1 and Hebrew labels).

## 0.4.0 (2026-11-05)

A run can be continued after a crash, the gate holds for Bash and for its own crashes, and the eval tooling gains a frozen suite and tagged failures.

### Resume and builders

- `/sdlc` resume: `/sdlc resume <slug>` (or a bare `/sdlc`, which lists runs that are not `closed` or `abandoned`) continues a run from its `status.md`. The file now opens with `run:`, `risk:`, `base:` and `plan-sha:`, and each stage line is `pending|running|done|skipped|blocked|failed`. `running` is written before a stage starts, so a crash leaves a mark.
- A fingerprint of the tracked and untracked changes (leaving out `.sdlc/`) is recorded as `built:` when Build is done. Resume compares it, and the plan's sha, and sends the run back to Verify or Plan when they differ. The gate is not changed, so `approve plan` is typed again on resume.
- Build: the builder runs the test files it wrote or changed plus the files the project's own related-tests command selects, in one foreground process and never while another agent runs tests. The one-test-file limit is gone from `/sdlc`, `rules/sdlc.md` and the three builder agents; the whole suite still runs at Ship.

### Gate

- A crash of the `tool` hook in a session that is locked or has an approved plan denies the action, with `sdlc off` as the way out. Without a lock, or with input that cannot name a session, it still fails open. The `prompt` hook never denies.
- While a session is locked, or a plan changed after approval, a Bash command that writes is denied for every agent, not only the read-only ones. The denial says to use the Write tool for files under `.sdlc/`; a redirect into `/tmp` is allowed. A locked command over 16,000 characters is denied as too long to check.
- A Bash command that spells `~/.claude/sdlc-gate/` (or the `SDLC_GATE_HOME` path) in a statement that writes is denied in every session. A commit message or heredoc that only quotes the folder is not a write. A relative path after `cd`, a glob or a variable is not seen.
- The write denylist covers inline code for `python`, `node`, `nodejs`, `ruby`, `perl`, `php`, `bun` and `deno eval` (also behind `sudo`, `env`, `VAR=x`, `uv run` and in a loop body), a shell or interpreter fed a heredoc, and `awk` that prints into a file, runs `system()` or edits in place. A heredoc body is no longer read as commands, for read-only agents too, unless the head pipes it on (`cat <<EOF | sh`).
- 68 new tests in `tests/test_sdlc_gate.py` and `tests/test_sdlc_gate_bypass.py`; 33 of the first 49 fail against the hook before this change, and the rest guard what must stay allowed.
- Known false positives while locked: read pipelines such as `npm test | tee out.log` or `git checkout -b x`. `approve plan` or `sdlc off` ends the lock.

### Eval suite and retro

- Eval suite: a frozen regression suite and a baseline per agent version. `scripts/suite.py freeze` records a hash of every file of each named case and never overwrites a manifest; `suite.py check` reports a case that changed or vanished after freezing, and, with `--baselines`, a baseline taken for another version of an agent file. `suite.py baseline` turns eval results into `<agent>-<hash>.json` (pass, error, cost and time of each run, in the shape `rate_lesson.py --regression` reads); a later result replaces a case's runs, and a case with an error, a skipped paid grader or fewer than 5 runs is listed as RERUN, as is (with `--manifest`) a frozen case of the agent that the results do not hold. The agent is taken from the agent file's name. A symlink inside a frozen case, and any unreadable or unwritable file, is an error (exit 2), never a crash. `scripts/check.sh` runs the check when `SDLC_EVALS` names the eval folder. The README and `/sdlc` describe the steps.
- Retro: failures are tagged and counted per task. The retro gains a **Failures** table (Tag, Stage, Agent, Root cause, Evidence, Resolution) with a fixed tag list, one row per distinct failure of the task. `scripts/failures.py` reads the tables under the folders it is given and prints, for each tag and agent, the number of different tasks that hit it with each task's evidence; a failure found by several checks, or written twice in one retro, counts once. A tag outside the list, a row without 6 cells or an unreadable retro is a PROBLEM line and exit 1; a retro written before the table is not a problem. The tag list is in the script and in `commands/sdlc.md`, and a test pins that they agree.
- Lessons library: a promotion is checked, and drift between the library and the installed agents is reported. Each fix has a test that failed before it.
  - `scripts/rate_lesson.py --regression <before.json>` compares every eval case that two runs share. A case that fell by half or more in pass rate is `REGRESSED`; the verdict goes to the lesson's `used` line, the exit code is 1 unless it is `ok`, and the lesson's status and confidence do not change. A baseline case the result lacks makes the verdict `confounded`, and the entry's key carries the `--agent` names, so records for two agents in one minute do not replace each other.
  - `scripts/rate_lesson.py --agent <file>` (repeatable) records the agent file's name and a short hash in the entry, so a rating says which version of the agent it rated.
  - `scripts/check_lessons.py`, called by `scripts/check.sh`, fails when a `promoted` lesson's quoted text is missing from an installed agent it names, and reports a rating whose agent file has changed since. It found `frontend-developer` without the L1 promotion (a local copy).
  - `/sdlc` and the README describe the steps: run the agent's eval cases before and after the edit.
- README: a diagram of the plugin (`docs/architecture.drawio`, rendered to `docs/architecture.png`). It shows the gate hooks and their state, the nine `/sdlc` stages with their agents and files, and the loop that improves the agents: the retro, the lessons library, the A/B rating, promotion into an agent file and the promotion check.

## 0.3.0 (2026-11-03)

The plan approval is bound to paths. Each fix has a test that failed before it; a few tests pin behaviour that already held.

- Gate hooks:
  - A plan can carry one `sdlc-scope` block (patterns relative to the project root). `approve plan` freezes it into the approval; afterwards only matching files can be edited with Edit, Write, MultiEdit or NotebookEdit, and a file outside it is denied with the way forward (add it to the plan, approve again). Files under `.sdlc/` stay writable. A plan without the block behaves as before.
  - When more than one `.sdlc/*/plan.md` exists and one holds a scope block (or a fence that looks like one), the reply is `approve plan <folder>`; a plain `approve plan` is refused and lists the plans. With no scope block anywhere, plain `approve plan` works as before. Every plan stays bound by its hash. A trailing full stop after the folder name is punctuation.
  - An approval is refused when the block cannot be read the way the owner reads it: an absolute path or `..`, a backslash, a control or invisible character, a pattern that matches nearly every file (alone or together), a first segment that can match `.git`, `.claude` or `.mcp.json`, an empty, unclosed or repeated block, a block inside another code fence, an indented or near-miss fence, more than 100 patterns.
  - A scope never covers `.git`, `.claude` or `.mcp.json`, wherever they sit; an edit there is denied whatever the patterns say.
  - A path written inside the project that resolves through a symlink to outside it is denied once a scope is frozen, also when the project directory is itself reached through a symlink. `[` and `]` in a pattern are plain characters.
  - The scope check denies instead of failing open when it cannot read its record. A file path the gate cannot read (a NUL, a lone surrogate, a non-string) is denied while a run is locked or approved; before, it exited non-zero and the host allowed the edit. `SDLC_GATE_SCOPE=off` turns off only the scope check.
  - A relative `file_path` is resolved against the session's `cwd`, not the hook's own directory; before, a relative path could slip past the lock. `NotebookEdit` is checked on both `file_path` and `notebook_path`. An approved record that is not a JSON object locks edits instead of crashing the hook.
  - The approval and each refusal are also sent as a `systemMessage`, so the owner sees them.
  - `approvals.log` records each approval's scope (`scope=none` when it is not path-limited) and each `deny-scope`.
- `tech-lead`: its Output gains a **Scope** section. The `/sdlc` Plan and Build rows describe the approval words and what a builder does with a denied file.

## 0.2.1 (2026-11-03)

Fixes from a code review of 0.2.0. Each code fix has a test that failed before it.

- Gate hooks:
  - The `Evidence:` check reads a `-F` message file from where the commit runs, after a `cd` or `git -C`, and checks every `git commit` in a command, not only the first.
  - When the gate cannot read the message (piped into `-F -`, or a `-F` file the same command writes first), it checks the text that supplies it: the pipe or heredoc into `-F -`, or the statement that writes the file. A `fix:` elsewhere in the command, or a command that only mentions `git commit -F`, is not affected.
  - A `git commit` line inside a heredoc body is text, not a commit. A `cd` inside quotes or a heredoc body does not move the message file. An empty heredoc and `$((1 << 3))` no longer hide later commits, and a `\` line continuation does not cut a statement.
  - The command is parsed only when it holds a `git commit`, and in linear time: heredoc bodies are found by scanning lines, not by one lazy regex. A command with more than 50 commits is denied as too many to check. Timing tests feed 150k to 300k characters of hostile input, and each is answered in well under the 5-second hook timeout.
  - `/sdlc off` in a session that is not gated no longer starts a run and locks it.
  - A `plan.md` that appears after the approval locks code edits, like one that changed.
  - Read-only agents may no longer create or copy a branch (`git branch <name>`, `-c`, `-C`, `-f`, `-u`, `-t`).
- `scripts/check.sh` checks that both hook events are wired, and reports `PARTIAL` as a problem when only one is.
- `scripts/rate_lesson.py`:
  - A run that skipped its paid graders, or an eval that stopped early, rates `confounded`.
  - `hurt` on a promoted lesson says to revert its text in the agent.
  - The confidence line tolerates trailing spaces.
  - Files are read and written as UTF-8.
- README: the rating command grants `--allow-tools Bash Write Edit`. Without it every run fails, and the rating is meaningless.
- `/sdlc` Build:
  - Repaired test setup does not count against the one-test-file limit.
  - A file left because its repair needs a choice goes to the owner, not to a builder.

## 0.2.0 (2026-11-03)

Gates that hold without the model's reading of a reply.

- Gate hooks (`plugins/sdlc/hooks/`):
  - Code edits are locked in an `/sdlc` session until the owner types `approve plan`. The approval is logged and bound to the hash of each `plan.md`, so a changed plan locks again. `sdlc off` releases.
  - A `fix:` commit without an `Evidence:` line is denied.
  - A Bash command from a read-only review agent that matches a denylist of common writes is denied (best effort, not a sandbox).
  - Checked in a real Claude Code host: a subagent's tool call carries the parent session's id, so the lock covers the builders too.
- `/security-audit` reports `Status: INCOMPLETE`, never `PASS`, when an agent fails, stops without a Status line or answers in an unreadable format.
- `/sdlc` Verify: a `security-reviewer` BLOCK stops the run until the fix is verified again or the owner accepts the risk in their own words.
- The whole suite runs on the release candidate. A change after it re-runs the tests it can affect, and the whole suite again when it touched shared code (`rules/sdlc.md`, `/sdlc` Ship).
- `scripts/check.sh` counts a missing rule as a problem and reports whether `settings.json` wires the hooks.
- Unit tests for the hooks in `tests/`.
- Lessons library: a rating needs a contrast.
  - A `/sdlc` run records each lesson it used as `confounded`. Only an A/B eval rates one `helped`, `hurt` or `no observed effect`: the same case, run with the lesson in the builder's plan and without it.
  - `scripts/rate_lesson.py` turns the eval's pass counts into that rating and writes it to `LESSONS.md`. `hurt` retires the lesson; `helped` sets `confidence: medium`.
  - A lesson from a retro enters as `proposed`. `tech-lead` applies it only after the owner accepts it.
  - Promoting a lesson into an agent needs `helped` from its A/B eval and the owner's yes. Before, it needed `helped` in two runs.
- `backend-developer` and `frontend-developer` fix what their change breaks outside the files they were given, and list each such file under **Outside the plan**. This replaces "stay in your lane", which had them stop and report.
  - The builder reports and leaves a file instead of editing it in three cases: another builder's task names the file, builders run in parallel, or the repair needs a choice the plan does not make.
  - A failing test that still states the intended behaviour means the change is wrong. Code the change does not break is left alone.
  - `/sdlc` keeps these files in `build.md`, `brutal-reviewer` checks each edit at Verify, and the retro reads each file as a plan miss.
  - `refactor-engineer` keeps "stay in your lane": a refactor that breaks a caller is itself wrong.
  - This promotes lesson L1. Its A/B eval scored with 3/3 and without 0/3: without the lesson, the builder found the broken callers but left them for a follow-up.

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
