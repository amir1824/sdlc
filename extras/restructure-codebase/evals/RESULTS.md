# Eval results: restructure-codebase

Measured with `claude plugin eval` on 2026-11-08, Claude Code 2.1.319, default model. Arms: **none** (no skill, same prompt), **original** (the `untangle-codebase` text this skill started from), **v1** (the first version of this skill) and **v2** (the current `SKILL.md`). Total spend for every run below, pilots included: about 16 USD.

## The hard case: `mess-service`

A 267-line order service, messy on purpose (`_shared/mess-fixture.sh`). The answer key is `_shared/MESS.md`. It covers 16 planted problems across the four kinds, 3 real bugs (fixing them changes behaviour and must be reported) and 3 traps that look like problems but must stay. The agent never sees the key.

`_shared/score-mess.mjs <workspace>` scores a finished run from the code, not from what the agent says. It checks each problem in the code reachable from `src/index.js`, runs the public API against the pristine fixture over fixed scenarios, and reads `REPORT.md` only to see whether each problem was named.

| | none | original | v1 | **v2** |
|---|---|---|---|---|
| runs | 3 | 3 | 3 | 5 |
| problems fixed (of 15) | 12.0 | 14.0 | 13.0 | **14.4** |
| bugs fixed (of 3) | 0.67 | 1.67 | 0.33 | **2.00** |
| bugs fixed and reported | 0.67 | 1.67 | 0.33 | **2.00** |
| traps kept (of 3) | 3.00 | 3.00 | 3.00 | 3.00 |
| behaviour changed without a reason | 0 | 0 | 0 | 0 |
| problems named in the report (of 16) | 15.7 | 15.7 | 15.7 | 15.0 |
| cost per run (USD) | 0.44 | 0.37 | 0.36 | 0.38 |

Per run, v2 fixed 14, 14, 15, 14 and 15 problems and 2 bugs every time. The original fixed 14 problems every time and 2, 2 and 1 bugs.

What the numbers say:

- **Finding is not the hard part.** Every arm, the no-skill one included, names almost every problem. The arms differ in what they then fix.
- **v1 made bug fixing worse than no skill.** Its rule "behaviour is the contract, ask the owner" led the agent to file real bugs as owner decisions and keep them. A v1 report says: *"Not changed (existing behaviour kept, owner decision): sending after `resetMailer()` without `init()` throws; `cancelled` cannot be set"*. It left the mailer's init-order bug in all 3 runs.
- **v2 fixes that.** It defines a bug as behaviour the code itself contradicts and says to fix it and log it, and to ask only about behaviour that looks intended. Bugs fixed went from 0.33 to 2.00 per run, with no trap broken and no unexplained change.
- **No arm ever fixed B1** (`cancelled` rejected by the status endpoint), in 14 runs. A refund also sets `cancelled`, so blocking it on the status route may be intended; the answer key is probably wrong to call it a bug.
- "Named in the report" is a keyword match and is noisy. v2's 15.0 comes from runs that fixed a problem without naming it in the words the matcher looks for.

### Limits

- 3 to 5 runs per arm, one fixture, one model. The gap between v2 and the original on problems (14.4 against 14.0) is within noise; the gap on bugs (2.00 against 1.67) is small. The gap between v1 and v2 on bugs is large and has a clear cause in the transcripts.
- The eval sandbox lets the agent write files with Write and Edit but not with Bash, and not delete them (`rm` and `git rm` fail with a read-only file system). The scorer therefore checks only code reachable from `src/index.js`, and the dead-file problem (S3) is counted as found only.
- The same author wrote the fixture, the answer key, the scorer and both skill versions, and ran every arm.

## The easy cases

| Case | What it checks | none | original | v1 |
|---|---|---|---|---|
| `shop-restructure` (5 runs) | a 123-line library: one tax rate, one formatter, the retry kept, a report that names an untested rounding difference | 1.00 | 1.00 | 1.00 |
| `shop-payments` (5 runs) | a third payment provider becomes a one-place change | 0.98 | 0.98 | 0.98 |
| `readme-typo` (3 runs) | must not fire on a one-line task | 1.00 | 1.00 | 1.00 |

Here every arm is at the ceiling, and `_shared/compare-golden.sh` confirmed that the public API was unchanged in every valid run. These cases show that the skill does no harm on small work and does not fire on a typo. They cannot rank the versions.

## Re-run

```bash
cd extras/restructure-codebase
claude plugin eval . --case mess-service --scaffold --trust-plugin --no-publish \
  --allow-tools Bash Write Edit Agent --runs 5 --keep-temp --json /tmp/rc/result.json
# for each run in the result, score its kept workspace (the sibling home/cwd of its tracePath):
node evals/_shared/score-mess.mjs /tmp/claude-eval-XXXX/home/cwd
```

The default ablation also runs the no-skill arm. To score another version of the skill, put its `SKILL.md` in a copy of this folder and run the same command with `--ablation none`. `--scaffold` needs `bubblewrap` and `socat`, because the runner refuses to give the agent Bash without a sandbox.
