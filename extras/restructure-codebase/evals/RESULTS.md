# Eval results: restructure-codebase

Measured with `claude plugin eval` on 2026-11-08, Claude Code 2.1.319, default model, one plugin arm (skill available) against a no-plugin baseline arm (same prompt, no skill). Total spend for all runs below, including pilots: about 10 USD.

## What was measured

| Case | What it checks | Runs per arm |
|---|---|---|
| `shop-restructure` | Restructure a 123-line shop library: one tax rate, one price formatter, restating comments and two useless tests gone, the retry kept with its external reason, tests green at the end, a `REPORT.md` that names the cart/invoice rounding difference (`Math.round` against `Math.floor`) that no test covers. | 5 |
| `shop-payments` | Make a third payment provider a one-place change, keep behaviour, touch nothing else. | 5 |
| `readme-typo` | Must not fire: fix one typo and use neither the skill nor edit `src/`. | 3 |

On top of the graders, `evals/_shared/compare-golden.sh <dir>` runs the library's public API over 220 inputs in a kept workspace and compares it with the pristine fixture. It is the ground truth for "behaviour did not change" and does not depend on what the agent says. A run that only hit the harness's read-only workspace (the agent reports it cannot write) is counted as an environment failure, not as a score.

## Results

| Case | No skill | Original `untangle-codebase` text | `restructure-codebase` |
|---|---|---|---|
| `shop-restructure` mean score (valid runs) | 1.00 (4 of 4 perfect) | 1.00 (5 of 5) | 1.00 (4 of 4) |
| `shop-payments` mean score | 0.98 (4 of 5 perfect) | 0.98 (4 of 5) | 0.98 (4 of 5) |
| `readme-typo` | 1.00 | 1.00 | 1.00 |
| Public API unchanged (ground truth, valid runs) | 9 of 9 | 10 of 10 | 9 of 9 |
| Runs lost to the read-only workspace | 1 | 0 | 1 |

The one miss in `shop-payments` is the same grader in all three arms (`behaviour-changes-reported`).

## What this does and does not show

- **No difference was measured.** On a fixture this small, a model with no skill already keeps the behaviour, names the rounding difference and writes an honest report, so every arm sits at the ceiling. The suite cannot tell the three apart.
- **The skill did run.** In the with-skill arm the `Skill` tool fired in every `shop-*` run of the first batch; the skill's own steps show in the transcripts (it tried to tag the base commit and wrote characterization tests). The `readme-typo` case confirms it does not fire on a one-line task.
- **The changes this version makes are about process** (a frozen base, a behaviour log kept as you go, a separate behaviour audit before the work is called done) and about a large codebase. A 123-line library does not exercise either. These changes are therefore **untested, not shown to help**.
- A first batch of 3 runs scored the new skill 0.74 against 1.00 for the baseline. That was one run that hit the read-only workspace plus a grader that tested a function's name; both were fixed (the graders now look for `toFixed`, the place where the logic was duplicated) and the cases re-run. The numbers above are from the re-run.

## To make the suite discriminate

Use a fixture where an unguided run fails: several hundred lines or more across areas, with behaviour that only a runtime or cross-module check reveals (a message another module parses, a default read from the environment), and score the ground-truth check as a grader. Then rerun with `--runs 5` and compare the three columns.

## Re-run

```bash
cd extras/restructure-codebase
claude plugin eval . --scaffold --trust-plugin --no-publish --allow-tools Bash Write Edit --runs 5 -j 4 --keep-temp --output-dir /tmp/rc-eval --json /tmp/rc-eval/result.json
# then, for each kept workspace (the result's tracePath, its sibling home/cwd):
evals/_shared/compare-golden.sh /tmp/claude-eval-XXXX/home/cwd
```

`--scaffold` needs `bubblewrap` and `socat` installed (the runner refuses to give the agent Bash without a sandbox). The scaffold scripts only write the fixture into the run's working directory.
