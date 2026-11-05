# Changelog

All notable changes, newest first. Versions follow [semver](https://semver.org): a change that alters how an agent or a gate behaves is a minor version, and a wording fix is a patch.

## 0.4.0 (2026-11-05)

The gate holds for Bash and for its own crashes. It still prevents mistakes, not attacks; the README says so.

- A crash of the `tool` hook in a session that is locked or has an approved plan denies the action, with `sdlc off` as the way out. Without a lock, or with input that cannot name a session, it still fails open. The `prompt` hook never denies.
- While a session is locked, or a plan changed after approval, a Bash command that writes is denied for every agent, not only the read-only ones. The denial says to use the Write tool for files under `.sdlc/`; a redirect into `/tmp` is allowed. A locked command over 16,000 characters is denied as too long to check.
- A Bash command that spells `~/.claude/sdlc-gate/` (or the `SDLC_GATE_HOME` path) in a statement that writes is denied in every session. A commit message or heredoc that only quotes the folder is not a write. A relative path after `cd`, a glob or a variable is not seen.
- The write denylist covers inline code for `python`, `node`, `nodejs`, `ruby`, `perl`, `php`, `bun` and `deno eval` (also behind `sudo`, `env`, `VAR=x`, `uv run` and in a loop body), a shell or interpreter fed a heredoc, and `awk` that prints into a file, runs `system()` or edits in place. A heredoc body is no longer read as commands, for read-only agents too, unless the head pipes it on (`cat <<EOF | sh`).
- 49 new tests in `tests/test_sdlc_gate.py`; 33 of them fail against the 0.3.0 hook, and the rest guard what must stay allowed.
- Known false positives while locked: read pipelines such as `npm test | tee out.log` or `git checkout -b x`. `approve plan` or `sdlc off` ends the lock.

## 0.3.0 (2026-11-05)

A run can be continued after a crash, and a builder is no longer limited to one test file.

- `/sdlc` resume: `/sdlc resume <slug>` (or a bare `/sdlc`, which lists runs that are not `closed` or `abandoned`) continues a run from its `status.md`. The file now opens with `run:`, `risk:`, `base:` and `plan-sha:`, and each stage line is `pending|running|done|skipped|blocked|failed`. `running` is written before a stage starts, so a crash leaves a mark.
- A fingerprint of the tracked and untracked changes (leaving out `.sdlc/`) is recorded as `built:` when Build is done. Resume compares it, and the plan's sha, and sends the run back to Verify or Plan when they differ. The gate is not changed, so `approve plan` is typed again on resume.
- Build: the builder runs the test files it wrote or changed plus the files the project's own related-tests command selects, in one foreground process and never while another agent runs tests. The one-test-file limit is gone from `/sdlc`, `rules/sdlc.md` and the three builder agents; the whole suite still runs at Ship.

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
