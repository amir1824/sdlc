# Changelog

All notable changes, newest first. Versions follow [semver](https://semver.org): a change that alters how an agent or a gate behaves is a minor version, and a wording fix is a patch.

## Unreleased

- README: a diagram of the plugin (`docs/architecture.drawio`, rendered to `docs/architecture.png`). It shows the gate hooks and their state, the nine `/sdlc` stages with their agents and files, and the loop that improves the agents: the retro, the lessons library, the A/B rating, promotion into an agent file and the promotion check.

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
  - Code edits are locked in an `/sdlc` session until the owner types `approve plan` or `אשר תוכנית`. The approval is logged and bound to the hash of each `plan.md`, so a changed plan locks again. `sdlc off` releases.
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
