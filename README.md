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
| `scripts/` | `install.sh` (rules, and optionally agents and commands, into `~/.claude`), `check.sh` (drift, hook wiring and version check) and `rate_lesson.py` (a lesson's A/B eval rating, written to the lessons library) |
| `tests/` | unit tests for the gate hooks and `rate_lesson.py` |

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

**3. Gate hooks** (`plugins/sdlc/hooks/`). A rule in a prompt holds only while the model reads it the way you meant, so the gates that must hold are hooks:

- **No code before the plan is approved.** Typing `/sdlc` locks code edits (Edit, Write, MultiEdit, NotebookEdit) in that session's project; files under `.sdlc/` stay writable. Typing `approve plan` or `אשר תוכנית` unlocks them, logs your words in `~/.claude/sdlc-gate/approvals.log`, and binds the approval to the hash of each `.sdlc/*/plan.md`: if a plan changes afterwards, code edits lock again until you approve it again. Any other reply, however positive, leaves the lock in place. `sdlc off` releases the session, for a LOW change you decide to do outside the pipeline.
- **`Evidence:` on `fix:` commits.** A `git commit` whose subject is `fix:` or `fix(scope):` and whose message has no `Evidence:` line is denied.
- **Read-only agents stay read-only, on a best-effort basis.** A Bash command from `tech-lead`, `security-reviewer`, `brutal-reviewer`, `analyst` or `leak-scanner` is denied when it matches a list of the common ways to write: a redirect into a file, `rm`/`mv`/`cp` and their kin, `sh -c`, in-place `sed` or `perl`, an install, `find -delete`, or a git command that changes state. It is a denylist, not a sandbox: `python3 -c` or `$(...)` gets through.

The gates stop a reply that was misread, not an agent set on getting past them. They need `python3` (3.9 or later) and fail open: an error or a timeout lets the action through, and `SDLC_GATE=off` turns them off. What they do not cover: a file written through Bash in a locked session, the gate's state in `~/.claude/sdlc-gate/`, which Bash can delete, and a run resumed in a new session, which needs `approve plan` typed again. `SDLC_GATE_TRACE=1` logs what Claude Code sends each hook to `~/.claude/sdlc-gate/trace.log`.

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

`/sdlc` can learn between runs:

- **At Plan,** `tech-lead` reads `~/.claude/lessons/LESSONS.md` when it exists. It applies the lessons whose cue fits the change, skipping `proposed` and `retired` ones, and verifies their facts first.
- **At the retro,** each lesson the plan used gets a row: what it changed and what was observed. One run has no contrast, so the row is rated `confounded`. At most one new lesson is added, as `proposed`, and `tech-lead` does not apply it until you accept it.
- **An A/B eval rates a lesson:** the same case run with the lesson in the builder's plan and without it. `hurt` retires the lesson, and `helped` raises its confidence to medium.
- **Agent files** never change from a run. Promoting a lesson into an agent needs `helped` from its A/B eval, and your yes.

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
2. Run both, at least 3 runs each:

   ```bash
   claude plugin eval <plugin> --case 'lesson-l1-*' --scaffold --ablation none --json result.json
   ```

3. Write the rating to the library, from a clone of this repo (the plugin does not install scripts):

   ```bash
   python3 -I scripts/rate_lesson.py result.json L1
   ```

   It counts the runs that passed in each arm. A gap of at least half in pass rate is `helped` or `hurt`, and a smaller gap is `no observed effect`. An errored run, or fewer than 3 runs in an arm, is `confounded`.

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
