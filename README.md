# sdlc

A risk-tiered software development lifecycle for [Claude Code](https://code.claude.com): role agents that plan, build, verify and ship, gates where a person decides, and evidence instead of claims.

The idea is to use the lightest process the risk allows. A one-line UI fix goes straight through, while an auth change waits for a design review and your yes. Every gate that is skipped is reported as skipped, and every check that did not run is reported as not run.

## What is inside

| Path | What |
|---|---|
| `plugins/sdlc/agents/` | 14 role agents: `tech-lead`, `product-manager`, `product-designer`, `analyst`, `user-researcher`, `backend-developer`, `frontend-developer`, `qa-engineer`, `brutal-reviewer`, `security-reviewer`, `refactor-engineer`, `devops-engineer`, `docs-engineer`, `leak-scanner` |
| `plugins/sdlc/commands/` | `/sdlc` (the full pipeline), `/brutal-review`, `/security-audit` |
| `rules/` | 7 engineering rules for `~/.claude/rules/`: principles, code standards, architecture and state, quality and testing, the SDLC itself, debugging and governance, frontend |
| `plugins/sdlc/hooks/` | the gate hooks (`sdlc_gate.py`, wired by `hooks.json`): no code before you approve the plan, `Evidence:` on `fix:` commits, read-only review agents stay read-only |
| `scripts/` | `install.sh` (rules, and optionally agents and commands, into `~/.claude`), `check.sh` (drift, hook wiring, version check, and promoted lessons missing from an installed agent), `rate_lesson.py` (a lesson's A/B eval rating and the regression check of a promotion, written to the lessons library), `check_lessons.py` (the promoted-lesson check `check.sh` calls), `failures.py` (counts the different tasks that hit the same tagged failure, from their retros) and `suite.py` (freezes eval cases by hash, and keeps a baseline per agent version) |
| `tests/` | unit tests for the gate hooks, `rate_lesson.py`, `check.sh`, `check_lessons.py`, `failures.py` and `suite.py` |
| `docs/` | `architecture.drawio`, the diagram below, and `architecture.png`, its rendered image |

![The plugin's parts and how they connect: the gate hooks, the nine /sdlc stages, and the loop that improves the agents](docs/architecture.png)

The diagram's labels are in Hebrew. Its source is `docs/architecture.drawio`: open it in draw.io or at [app.diagrams.net](https://app.diagrams.net), and export it again to `docs/architecture.png` after a change.

## How it works

**1. Classify the risk first** (`rules/sdlc.md`).

| Risk | Examples | Process |
|---|---|---|
| LOW | small UI change, local refactor, docs, isolated bug fix | Do it, then verify it with the one check that proves it. |
| MEDIUM | new feature, shared component, API behaviour change | A short plan with acceptance criteria, then build, test, and an independent review. |
| HIGH | auth, migrations, concurrency, infrastructure, anything security-sensitive | Design review with failure analysis and rollback; you say yes before the first edit. |

**2. `/sdlc` for a feature that starts from an idea.** It runs nine stages, and each one writes a handoff file in `.sdlc/<slug>/`. The files, not the chat, are the project's memory.

| # | Stage | Agent | Writes |
|---|---|---|---|
| 1 | Discover | `user-researcher`, or an `intent.md` when you state the problem | `research.md` / `intent.md` |
| 2 | Define (**STOP**: you approve scope) | `product-manager`, `analyst` | `prd.md`, `metrics.md` |
| 3 | Design (skipped without UI) | `product-designer` | `design-spec.md` |
| 4 | Plan (**STOP**: you approve the plan) | `tech-lead`, `security-reviewer` on the plan | `plan.md` |
| 5 | Build | `backend-developer`, `frontend-developer` | code, `build.md` |
| 6 | Verify | `qa-engineer`, `brutal-reviewer`, `security-reviewer` | `review.md` |
| 7 | Ship | `devops-engineer`, `docs-engineer`, `leak-scanner` | `release.md` |
| 8 | Launch (optional, needs `/campaign`) | marketing | `launch.md` |
| 9 | Learn (on the readout date) | `analyst` | `learn.md` |

The plan carries a requirement map (every requirement ID to its files and its proving check). It also has an **Instances** section: every call site, sibling or key family a change must cover, with the grep that found them. Trust boundaries are named before any code exists. A builder fixes what its change breaks outside its files and lists each one under **Outside the plan** in `build.md`. It reports instead of editing when the file belongs to another builder or the repair needs a choice the plan does not make. The retro reads each one as a plan miss, so the next plan can list it. A failed gate sends the work back to the stage that owns the fix. Nothing is committed, pushed or published unless you ask.

A run survives a closed session: `status.md` records each stage as `pending`, `running`, `done`, `skipped`, `blocked` or `failed`, with the run's base commit and the plan's hash. `/sdlc resume <slug>` re-runs the stage a crash left `running`. It compares the plan and a fingerprint of the built code with the recorded ones, and sends the run back to Plan or Verify when they differ. The gate hook locks the session again on `/sdlc`, so you type `approve plan` again.

**3. Gate hooks** (`plugins/sdlc/hooks/`). A rule in a prompt holds only while the model reads it the way you meant, so the gates that must hold are hooks:

- **No code before the plan is approved.** Typing `/sdlc` locks code edits (Edit, Write, MultiEdit, NotebookEdit) in that session's project; files under `.sdlc/` stay writable. Typing `approve plan` or `אשר תוכנית` unlocks them, logs your words in `~/.claude/sdlc-gate/approvals.log`, and binds the approval to the hash of each `.sdlc/*/plan.md`: if a plan changes, or a new one appears, afterwards, code edits lock again until you approve again. Any other reply, however positive, leaves the lock in place. When more than one `.sdlc/*/plan.md` exists and one of them holds a scope block, you reply `approve plan <folder>` to say which plan you approve. When that plan holds an `sdlc-scope` block (one pattern per line, relative to the project root), the approval freezes it: afterwards only matching files can be edited, and a file outside it is denied until you change the plan and approve again. A scope never covers `.git`, `.claude` or `.mcp.json`, wherever they sit. The gate refuses to approve a block it cannot read the way you do: a pattern that matches nearly every file, an absolute path or `..`, a control character, a block inside another code fence, more than one block. A plan without the block is not path-limited, and the log says `scope=none`. The approval and any refusal are also shown to you, not only sent to the model. `sdlc off` releases the session, for a LOW change you decide to do outside the pipeline.
- **`Evidence:` on `fix:` commits.** A `git commit` whose subject is `fix:` or `fix(scope):` and whose message has no `Evidence:` line is denied. Every commit in the command is checked, and a `-F` file is read from where the commit runs (after a `cd` or `git -C`). When it cannot read the message (piped into `-F -`, or a `-F` file the same command writes first), it checks the text that supplies it, the pipe or heredoc into `-F -` or the statement that writes the file, for a `fix:` subject and an `Evidence:` line.
- **Read-only agents stay read-only, on a best-effort basis.** A Bash command from `tech-lead`, `security-reviewer`, `brutal-reviewer`, `analyst` or `leak-scanner` is denied when it matches a list of the common ways to write: a redirect into a file, `rm`/`mv`/`cp` and their kin, `sh -c`, inline code (`python3 -c`, `node -e`, `perl -e`, an interpreter fed a heredoc), `awk` that writes, in-place `sed` or `perl`, an install, `find -delete`, or a git command that changes state. It is a denylist, not a sandbox: a script file that writes, a verb built at run time, a quoted verb and any verb not listed get through, and some spellings are missed (`python3 -W error -c`, `awk` printing into a pipe).

The gates prevent mistakes, not attacks: they stop a reply that was misread and a model's slip, not an agent set on getting past them. They are guardrails for the workflow, and they do not show that the requirements are right or complete: passing checks show the checks passed, not that the criteria are the right ones. For HIGH work the plan lists what must not happen and the assumptions about the request, so the owner can catch a missing requirement before code exists. This plugin's gates are a best-effort guardrail; an action that must never happen belongs in Claude Code's permission deny rules or a sandbox. They need `python3` (3.9 or later). A crash of the tool hook in a session that is locked or has an approved plan denies the action (reply `sdlc off` to release the session); so does the scope check, and so does a file path the gate cannot read there. With no lock, or input that cannot name a session, an error lets the action through, and a timeout lets it through even when gated; `SDLC_GATE=off` turns the gates off, `SDLC_GATE_SCOPE=off` only the scope check. While a session is locked, or a plan changed after you approved it, a Bash command that writes is denied for every agent (write files under `.sdlc/` with the Write tool, which creates the folders; a redirect into `/tmp` is allowed). Some read pipelines are denied then too, such as `npm test | tee out.log` or `git checkout -b x`; `approve plan` or `sdlc off` ends that. A Bash command that spells `~/.claude/sdlc-gate/` and writes is denied in any session (a relative path after `cd`, a glob or a variable is not seen). A Bash write is judged by a denylist (redirects, `rm`, `git commit`, `python -c`, `node -e` and similar), not a sandbox: a verb it does not list, a script file that writes, or a path built at run time gets through, a scope pattern is not checked for Bash, an edit outside `CLAUDE_PROJECT_DIR` (a sibling package of a larger repo) is never gated, and a run resumed in a new session needs `approve plan` typed again. A boundary that holds against a hostile model needs enforcement outside the model, such as an OS sandbox; this plugin does not provide one. `SDLC_GATE_TRACE=1` logs what Claude Code sends each hook to `~/.claude/sdlc-gate/trace.log`.

## Install

**The agents and commands, as a plugin:**

```
/plugin marketplace add amir1824/sdlc
/plugin install sdlc@sdlc
```

**The rules** (recommended, since the agents assume them):

```bash
git clone https://github.com/amir1824/sdlc.git && cd sdlc && scripts/install.sh
```

`install.sh` copies the rules into `~/.claude/rules/`. Any file it replaces is moved to `~/.claude/.sdlc-backup/<time>/` first. Nothing is deleted.

**If you maintain this repo,** link instead of copying, so you edit in one place and `git pull` updates your install:

```bash
scripts/install.sh --link --agents
```

`--agents` also puts the agents and commands straight into `~/.claude` without the plugin's namespace. Do not combine it with the plugin install, or each agent appears twice.

Plugin hooks load only with the plugin, so a `--link --agents` install wires them in `~/.claude/settings.json` (back the file up first; `scripts/check.sh` shows `linked` once it is there):

```json
"hooks": {
  "UserPromptSubmit": [
    { "hooks": [{ "type": "command", "command": "python3 -I /path/to/sdlc/plugins/sdlc/hooks/sdlc_gate.py prompt", "timeout": 5 }] }
  ],
  "PreToolUse": [
    { "matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash",
      "hooks": [{ "type": "command", "command": "python3 -I /path/to/sdlc/plugins/sdlc/hooks/sdlc_gate.py tool", "timeout": 5 }] }
  ]
}
```

To keep your own version of a file, for example an agent with your own MCP connectors in its `tools:` line, list it in `~/.claude/.sdlc-local-overrides`, one path per line (`agents/product-manager.md`). `install.sh` never replaces a listed file, and `check.sh` shows it as `local`.

## Optional skills

Some gates call skills from other plugins: `idea-slayer` and `architecture-slayer` (Anthropic skills), and `change-impact`, `browser-qa`, `click-path-audit` and `canary-watch` (ECC). When one is not installed, the stage says "not run" at the top of its file instead of inventing a verdict. A few agents also name ECC skills in their "load when they fit" lists; those lists are optional.

## A lessons library (optional)

`/sdlc` can learn between runs (the green box in the [diagram](docs/architecture.png) draws the whole loop):

- **At Plan,** `tech-lead` reads `~/.claude/lessons/LESSONS.md` when it exists. It applies the lessons whose cue fits the change, skipping `proposed` and `retired` ones, and verifies their facts first.
- **At the retro,** each lesson the plan used gets a row: what it changed and what was observed. One run has no contrast, so the row is rated `confounded`. At most one new lesson is added, as `proposed`, and `tech-lead` does not apply it until you accept it.
- **Every failure is tagged.** The retro's **Failures** table gives each distinct failure of the task a row: a tag from a fixed list, the stage that caught it, the agent, a root cause, the evidence and the resolution. `python3 -I scripts/failures.py <project folders>` counts the different tasks per tag and agent, so a failure that recurs across tasks is visible before anyone proposes a lesson for it. It counts a failure once per task, and reports a row with a tag outside the list.
- **An A/B eval rates a lesson:** the same case run with the lesson in the builder's plan and without it. `hurt` retires the lesson, and `helped` raises its confidence to medium. A promoted lesson that is later rated `hurt` also needs its text reverted in the agent it was written into; the script says so.
- **Agent files** never change from a run. Promoting a lesson into an agent needs `helped` from its A/B eval, and your yes. After the edit, a regression check runs all of that agent's eval cases against a run from before it, and an edit that made a case worse is reverted.

To start a library, create the file with entries like this (an entry you write yourself can start as `library`; one the retro adds starts as `proposed`):

```markdown
## L1 · backend-developer · INV
- cue: a change alters a function's signature that other code calls
- lesson: grep every call site, tests included, and update each before reporting done
- evidence: <the run and the finding>
- confidence: low
- status: library
- used: none yet
```

To rate a lesson:

1. In your plugin's eval suite, write two cases named `lesson-<id>-with` and `lesson-<id>-without`. They share the prompt, the graders and the scaffold, and differ only in the lesson's line in the builder's plan. The graders check the operation the lesson names, for example that no file still calls the old signature.
2. Run both, at least 3 runs each. Grant the tools the builder edits with: without `--allow-tools`, every run of both arms fails, and the rating says `no observed effect` about nothing. Add `--trust-plugin` when the run cannot stop to ask, and export `SDLC_GATE=off` when a case's prompt starts with `/sdlc`.

   ```bash
   claude plugin eval <plugin> --case 'lesson-l1-*' --scaffold --ablation none --allow-tools Bash Write Edit --json result.json
   ```

3. Write the rating to the library, from a clone of this repo (the plugin does not install scripts):

   ```bash
   python3 -I scripts/rate_lesson.py result.json L1
   ```

   It counts the runs that passed in each arm. A gap of at least half in pass rate is `helped` or `hurt`, and a smaller gap is `no observed effect`. An errored run, a run that skipped its paid graders, an eval that stopped early, or fewer than 3 runs in an arm is `confounded`.

To promote a rated lesson (after `helped` and your yes), check that the agent edit broke nothing else. The frozen suite, the baselines and the hidden holdout live with the plugin's evals (here `my-agents-plugin/evals`, `evals/baselines` and `evals-holdout`):

1. **Freeze once.** `python3 -I scripts/suite.py freeze evals/suites/regression.json evals <case> ...` records a hash of every file of each case, and refuses to overwrite a manifest. `scripts/check.sh` runs `suite.py check` when `SDLC_EVALS` names the eval folder (`export SDLC_EVALS=~/claude-mods/my-agents-plugin/evals`): a case that was edited after freezing is CHANGED, and a baseline taken for another version of the agent file is `stale`.
2. **A baseline per agent version.** Run the agent's cases (`claude plugin eval <plugin> --case '<agent>-*' --scaffold --ablation none --allow-tools Bash Write Edit --trust-plugin --json result.json`, 5 runs each), then `python3 -I scripts/suite.py baseline result.json --agent-file <the plugin's agents/<agent>.md> --out evals/baselines --manifest evals/suites/regression.json`. It keeps each run's pass, error, cost and time in `<agent>-<hash>.json`, where the hash names the agent file. A case it lists as RERUN (a timeout, a skipped paid grader, fewer than 5 runs, a frozen case missing from the results) is run alone, and its result file is added to the same command: a later result replaces that case's runs.
3. **Edit, then run again.** Edit the agent, sync the plugin's copy, and run the same cases into `after.json`, and the hidden holdout (`--eval-dir evals-holdout`, a baseline kept in `evals-holdout/baselines`) the same way.
4. **Record the comparison,** naming the agent file so the entry carries its hash:

   ```bash
   python3 -I scripts/rate_lesson.py after.json L1 --regression evals/baselines/<agent>-<hash>.json --agent plugins/sdlc/agents/<agent>.md
   ```

   A case that both runs hold, with at least 3 runs and no error or skipped paid grader in each, is judged, and it dropped when its pass rate fell by half or more. `ok` means none dropped. `REGRESSED` names the cases and exits 1: revert the edit, or fix it and run both again. `confounded` (nothing judged, or the eval stopped early) exits 1 too, since it shows nothing. The lesson's status and confidence do not change.

`scripts/check.sh` then reports a promoted lesson whose quoted text is missing from an installed agent (a local copy that never got the edit), and a rating whose agent file has changed since.

## Versions

- `plugins/sdlc/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` carry the same [semver](https://semver.org) version, and `scripts/check.sh` fails when they differ.
- Each release adds an entry to `CHANGELOG.md` and a git tag `vX.Y.Z`.
- To update: plugin users run `/plugin marketplace update sdlc`. With `--link`, `git pull` is enough. With a copy, run `scripts/install.sh` again.
- `scripts/check.sh` lists every installed file as linked, same, DRIFT or missing, so you can see a local edit that never made it back to the repo. A rule that is not installed shows as MISSING and fails the check, since the plugin does not ship rules.

## Changing it

1. Edit the agent, command or rule in this repo.
2. Run `scripts/check.sh` and `python3 -I -m unittest discover -s tests`.
3. Bump the version in both JSON files and add a `CHANGELOG.md` entry.
4. Open a pull request.

A change to how the agents behave is worth an eval run before it ships.
