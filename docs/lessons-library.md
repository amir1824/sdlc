# The lessons library (optional)

`/sdlc` can learn between runs (the green box in the [diagram](architecture.png) draws the whole loop):

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

1. **Freeze once.** `python3 -I scripts/suite.py freeze evals/suites/regression.json evals <case> ...` records a hash of every file of each case, and refuses to overwrite a manifest. `scripts/check.sh` runs `suite.py check` when `SDLC_EVALS` names the eval folder (`export SDLC_EVALS=~/claude-mods/my-agents-plugin/evals`): a case that was edited after freezing is CHANGED, and a baseline taken for another version of the agent file is `stale` and exits 1 (take a new baseline before comparing).
2. **A baseline per agent version.** Run the agent's cases (`claude plugin eval <plugin> --case '<agent>-*' --scaffold --ablation none --allow-tools Bash Write Edit --trust-plugin --json result.json`, 5 runs each), then `python3 -I scripts/suite.py baseline result.json --agent-file <the plugin's agents/<agent>.md> --out evals/baselines --manifest evals/suites/regression.json`. It keeps each run's pass, error, cost and time in `<agent>-<hash>.json`, where the hash names the agent file. Add `--config <path>` (repeatable: the `/sdlc` command, the rules, the hooks, the skills) and the baseline also records a hash of every file under those paths; `suite.py check` then calls the baseline `stale` when one changed, vanished or appeared, since the agent file alone does not hold everything the agent runs with. A baseline taken without `--config` says nothing about them. The model and the evaluator are not recorded beyond the Claude version. A case it lists as RERUN (a timeout, a skipped paid grader, fewer than 5 runs, a frozen case missing from the results) is run alone, and its result file is added to the same command: a later result replaces that case's runs.
3. **Edit, then run again.** Edit the agent, sync the plugin's copy, and run the same cases into `after.json`, and the hidden holdout (`--eval-dir evals-holdout`, a baseline kept in `evals-holdout/baselines`) the same way.
4. **Record the comparison,** naming the agent file so the entry carries its hash:

   ```bash
   python3 -I scripts/rate_lesson.py after.json L1 --regression evals/baselines/<agent>-<hash>.json --agent plugins/sdlc/agents/<agent>.md
   ```

   A case that both runs hold, with at least 3 runs and no error or skipped paid grader in each, is judged, and it dropped when its pass rate fell by half or more. A case named with `--hard-gate <case>` (repeatable; use it for safety, security and approval cases) dropped on any fall in pass rate: 5/5 to 3/5 is `REGRESSED` for it, not for an ordinary case. `ok` means every case was judged and none dropped. `REGRESSED` names the cases and exits 1: revert the edit, or fix it and run both again. `confounded` exits 1 too, since it shows nothing: nothing judged, a case in both files that could not be judged (fewer than 3 runs, an error, a skipped paid grader), a baseline case or a `--hard-gate` case missing from a file, or the eval stopped early. Run the unjudged case again; the edit is not promoted until the verdict is `ok`. Add `--max-cost-ratio R` to price the edit too: cost per accepted task is every run's `costUsd`, failures included, over the runs that passed, summed over the judged cases. When it grew by more than R times the baseline's, the verdict is `COSTLY` and exits 1; keep the edit only if the cost is yours to accept. A run without `costUsd`, or a baseline with no passing run, is `confounded`. Without the flag cost is not looked at, and the ratio is yours to choose: nothing here says what a pass is worth. The lesson's status and confidence do not change.

`scripts/check.sh` then reports a promoted lesson whose quoted text is missing from an installed agent (a local copy that never got the edit), and a rating whose agent file has changed since.
