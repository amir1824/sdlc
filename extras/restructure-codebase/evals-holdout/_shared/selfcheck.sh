#!/usr/bin/env bash
# Self-check for the holdout-service eval: the fixture's tests pass, the scorer gives the pristine
# fixture nothing, and the scorer reacts correctly to scripted edits (a real fix is credited, a bug
# fix is credited without counting as an unexplained change, a broken trap or runtime-only
# behaviour is caught, and the reference restructure gets full marks).
# Usage: bash selfcheck.sh   (prints PASS/FAIL per check, exits non-zero on any FAIL)
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
for v in $(env | grep -o '^LENDWELL_[A-Z_]*' || true); do unset "$v"; done
fails=0
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1${2:+: $2}"; fails=$((fails + 1)); }

fresh() { # fresh <name>: a new copy of the pristine fixture in $work/<name>
  mkdir -p "$work/$1" && (cd "$work/$1" && bash "$here/fixture.sh") || { echo "fixture.sh failed" >&2; exit 2; }
}
mutate() { # mutate <dir> <file> <old> <new>: exact replacement; fails loudly if <old> is absent
  node -e '
    const fs = require("fs"); const [f, a, b] = process.argv.slice(1);
    const s = fs.readFileSync(f, "utf8");
    if (!s.includes(a)) { console.error("mutation target not found in " + f + ": " + a); process.exit(3); }
    fs.writeFileSync(f, s.split(a).join(b));' "$1/$2" "$3" "$4" || { echo "mutation failed" >&2; exit 2; }
}
score() { node "$here/score.mjs" "$work/$1" > "$work/$1.score.json" 2> "$work/$1.score.err" || echo '{"crashed":true}' > "$work/$1.score.json"; }
expect() { # expect <label> <score name> <js boolean expression over r>
  if node -e '
    const r = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
    const ok = (function () { return eval(process.argv[2]); })();
    if (!ok) { const { problems, found, bugsReported, ...brief } = r; console.error(JSON.stringify(brief)); process.exit(1); }' \
    "$work/$2.score.json" "$3" 2> "$work/expect.err"; then pass "$1"; else fail "$1" "$(head -c 600 "$work/expect.err")"; fi
}

# (a) the fixture builds and its tests pass (one planted skip allowed)
fresh pristine
if (cd "$work/pristine" && npm test > "$work/npm.out" 2>&1); then
  if grep -q '^# fail 0' "$work/npm.out" && grep -q '^# skipped 1' "$work/npm.out"; then pass "a: fixture npm test passes (1 planted skip)"; else fail "a: fixture npm test summary" "$(grep '^# ' "$work/npm.out" | tr '\n' ' ')"; fi
else
  fail "a: fixture npm test" "$(tail -5 "$work/npm.out")"
fi
lines=$(cat $(find "$work/pristine/src" -name '*.js') | wc -l)
areas=$(find "$work/pristine/src" -mindepth 1 -maxdepth 1 -type d | wc -l)
if [ "$lines" -ge 2000 ] && [ "$lines" -le 4000 ] && [ "$areas" -ge 6 ]; then pass "a: src/ is $lines lines in $areas areas"; else fail "a: size" "$lines lines, $areas areas"; fi
fresh twice
if diff -r -x .git "$work/pristine" "$work/twice" > /dev/null; then pass "a: fixture.sh is deterministic"; else fail "a: fixture.sh is deterministic"; fi

# (b) the pristine fixture scores nothing
score pristine
expect "b: pristine scores 0 fixed, 0 bugs, all traps kept, 0 unexplained" pristine \
  'r.problemsFixed === 0 && r.bugsFixed === 0 && r.trapsKept === r.trapsTotal && r.unexplainedBehaviourChanges.length === 0 && r.problemsFound === 0'
expect "b: answer key size (>=25 problems, >=4 bugs, >=4 traps)" pristine 'r.problemsTotal >= 25 && r.bugsTotal >= 4 && r.trapsTotal >= 4'

# (c1) genuine structural fixes are credited, and only those
fresh fix-problem
mutate "$work/fix-problem" src/shared/money.js "import { CURRENCY } from '../admin/settings.js';" "const CURRENCY = process.env.LENDWELL_CURRENCY || 'USD';"
mutate "$work/fix-problem" src/shared/dates.js $'\nexport { addDays as plusDays };\n' $'\n'
mutate "$work/fix-problem" src/fines/fines.js $'\nexport { FINE_PER_DAY, MAX_FINE_CENTS } from \'./fine-rates.js\';\n' $'\n'
mutate "$work/fix-problem" src/catalog/item-types.js $'\nexport default ITEM_TYPES;\n' $'\n'
score fix-problem
expect "c1: fixing N2 and S4 credits exactly those two, no behaviour change" fix-problem \
  'r.problems["N2 money formatting imports admin settings"] && r.problems["S4 re-exports nobody uses"] && r.problemsFixed === 2 && r.bugsFixed === 0 && r.unexplainedBehaviourChanges.length === 0'

# (c2) a bug fix is credited and is not an unexplained change
fresh fix-bug
mutate "$work/fix-bug" src/circulation/loans.js "if (loan.renewals > MAX_RENEWALS) {" "if (loan.renewals >= MAX_RENEWALS) {"
score fix-bug
expect "c2: fixing B4 is credited, nothing unexplained" fix-bug \
  'r.bugs["B4 renewLoan allows a third renewal"] && r.bugsFixed === 1 && r.unexplainedBehaviourChanges.length === 0 && r.trapsKept === r.trapsTotal'

# (c3) the start-up bug fixed in the notifier itself
fresh fix-init
mutate "$work/fix-init" src/notifications/notifier.js "const template = templates[kind];" "const template = (templates ??= loadTemplates())[kind];"
score fix-init
expect "c3: fixing B2 is credited, nothing unexplained, H5 still open (admin still gates)" fix-init \
  'r.bugs["B2 notices crash or vanish unless startNotifications ran"] && r.bugsFixed === 1 && r.unexplainedBehaviourChanges.length === 0 && !r.problems["H5 notices need startNotifications() first; only the admin API calls it"]'

# (c4) patching the copy that has the bug fixes the bug but not the duplicated list
fresh patch-copy
mutate "$work/patch-copy" src/admin/handlers.js "const ALLOWED_TYPES = ['book', 'dvd', 'magazine', 'map'];" "const ALLOWED_TYPES = ['book', 'dvd', 'magazine', 'audiobook', 'map'];"
score patch-copy
expect "c4: adding audiobook to the admin copy fixes B1 but not H1" patch-copy \
  'r.bugs["B1 admin API rejects audiobooks"] && !r.problems["H1 item-type list copied (catalog, admin, reports)"] && r.unexplainedBehaviourChanges.length === 0'

# (c5) removing the Paywell retry breaks a trap
fresh break-retry
mutate "$work/break-retry" src/fines/payments.js "if (err?.code !== 'ETIMEDOUT') throw err;" "throw err;"
score break-retry
expect "c5: removing the justified retry is caught as a broken trap" break-retry \
  '!r.traps["T1 Paywell timeout retried exactly once"] && r.unexplainedBehaviourChanges.some((k) => k.startsWith("TRAP payment"))'

# (c6) "unifying" the senior rounding with Math.round breaks a trap
fresh break-rounding
mutate "$work/break-rounding" src/fines/fines.js "total = Math.floor((total * 2) / 3);" "total = Math.round((total * 2) / 3);"
score break-rounding
expect "c6: rounding seniors to nearest is caught as a broken trap" break-rounding '!r.traps["T3 seniors pay two thirds rounded down"]'

# (c7) runtime-only behaviours: env fallback and the wording the digest parses
fresh break-env
mutate "$work/break-env" src/admin/settings.js "process.env.LENDWELL_CURRENCY || 'USD'" "process.env.LENDWELL_CURRENCY ?? 'USD'"
score break-env
expect "c7: ?? instead of || for LENDWELL_CURRENCY is an unexplained change" break-env \
  'r.unexplainedBehaviourChanges.includes("env currency empty falls back to USD")'
fresh break-wording
mutate "$work/break-wording" src/notifications/templates.js 'is ready for pickup at ${branchName} until ${until}.' 'is waiting for you at ${branchName} until ${until}.'
score break-wording
expect "c7: rewording the hold-ready notice breaks the pickup digest" break-wording \
  'r.unexplainedBehaviourChanges.includes("main hold shelf expiry") && r.unexplainedBehaviourChanges.includes("hold flow")'

# (c8) the reference restructure: every problem fixed, every bug fixed, traps kept, tests green
fresh reference
(cd "$work/reference" && bash "$here/reference-fix.sh") || fail "c8: reference-fix.sh ran"
if (cd "$work/reference" && npm test > "$work/ref-npm.out" 2>&1) && grep -q '^# skipped 0' "$work/ref-npm.out"; then pass "c8: reference restructure npm test passes, no skips"; else fail "c8: reference npm test" "$(grep '^# ' "$work/ref-npm.out" | tr '\n' ' ')"; fi
cat > "$work/reference/REPORT.md" <<'EOF'
To delete: src/catalog/marc-import.js (the Dynix import nothing calls).
EOF
score reference
expect "c8: reference restructure scores full marks with nothing unexplained" reference \
  'r.problemsFixed === r.problemsTotal && r.bugsFixed === r.bugsTotal && r.trapsKept === r.trapsTotal && r.unexplainedBehaviourChanges.length === 0'
expect "c8: a file listed under To delete counts as found" reference 'r.found["S3 dead Dynix import module (marc-import.js)"] === true && r.problemsFound === 1'

# (c9) a workspace whose public API no longer loads gets no behaviour credit
fresh broken
mutate "$work/broken" src/index.js "export { formatCents } from './shared/money.js';" "export { formatCents } from './shared/nowhere.js';"
score broken
expect "c9: a broken public API scores no bugs and flags the break" broken \
  'r.bugsFixed === 0 && r.trapsKept === 0 && r.unexplainedBehaviourChanges.length > 0'

echo
if [ "$fails" -eq 0 ]; then echo "ALL CHECKS PASS"; else echo "$fails CHECK(S) FAILED"; fi
exit $((fails > 0))
