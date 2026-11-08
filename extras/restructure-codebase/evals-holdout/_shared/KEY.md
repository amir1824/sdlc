# holdout-service answer key (lendwell)

Held-out case for a "restructure a whole codebase" skill. **Keep this file away from the agent under
test**; the scaffold only writes the fixture.

## The fixture

`fixture.sh` writes **lendwell 2.4.1**: the lending service of a county library system (members,
catalogue, loans, holds, fines, notices, reports, operator API). Node 22 ESM, no dependencies,
`npm test` = `node --test` (33 pass, 1 planted skip).

- `src/`: 2,146 lines, 48 files, 9 areas: `shared`, `members`, `catalog`, `circulation`, `holds`,
  `fines`, `notifications`, `reports`, `admin` (plus `config.js` and `index.js`).
- Public API: the 56 names exported from `src/index.js`.
- README.md states the circulation policy; it is the reference for "intended" behaviour.

Line numbers below are for the pristine fixture.

## Files

| File | Purpose |
| --- | --- |
| `fixture.sh` | Writes the repo into the current directory, one git commit with fixed dates (git failure tolerated). |
| `golden.mjs <ws>` | Drives only the public API over 61 fixed scenarios; prints JSON. `BUG ` keys are planted bugs, `TRAP ` keys must never change. Env-dependent scenarios run in child processes. |
| `score.mjs <ws>` | One JSON line: problems fixed/found, bugs fixed/reported, traps kept, unexplained behaviour changes, per-item booleans, misses. |
| `reference-fix.sh` | A complete reference restructure (writes files only, like the agent). Used by the selfcheck to prove full marks are reachable. |
| `selfcheck.sh` | Builds, tests, scores the pristine fixture, and checks the scorer's reaction to 10 scripted edits. |

Scoring rules: structure is judged **from code only**, on the files reachable from `src/index.js`
through static imports (a file nothing imports counts as gone, since the sandbox cannot delete).
Comments are stripped before code checks. Behaviour is judged by diffing `golden.mjs` on the workspace
against a freshly built pristine fixture. "Found" is a keyword match in `REPORT.md` and never counts
as "fixed".

## Problems (28: 27 scored from code, 1 found-only)

Kinds: hidden links 10, needless links 6, surplus 5, special cases 5, restating comments 1 item
(10 comments), weak tests 1 item (5 tests). "Wide" = spans 3+ files or 2+ areas (18 of 28).

### Hidden links

| Id | Where | Wide | What is wrong | Counts as fixed when (reachable code) |
| --- | --- | --- | --- | --- |
| H1 | `catalog/item-types.js:3`, `admin/handlers.js:34`, `reports/circulation-report.js:9` | yes | Item-type list kept three times; the admin copy has drifted (bug B1). | At most one file has an array literal listing 3+ type names. |
| H2 | `circulation/loan-policy.js:3` (`LOAN_DAYS`), `fines/fine-rates.js:2` (`FINE_PER_DAY`) | yes | Per-type properties in two tables in two areas, keyed by the same types; adding a type means editing both (plus H1). | At most one file has an object keyed by 3+ type names. |
| H3 | `shared/calendar.js:8` `export let closedDates`, set via `setClosedDates` (admin `handlers.js:182`, public API), read as a live binding in `circulation/due-dates.js:2,7` | yes | Module-level mutable state written in one module, read in another. | No `export let/var` named like closed/holiday/calendar and nobody imports `closedDates`. |
| H4 | `notifications/notifier.js:9` `export let outbox`, reassigned at `:36`, read as a live binding by `reports/notice-digest.js:4,10` | yes | Same, across notifications and reports. | No `export let/var` named like outbox/sent/message and nobody imports `outbox`. |
| H5 | `notifications/notifier.js:6,11-17,20,35`; only `admin/http.js:5,82` performs `startNotifications()`; `circulation/loans.js:117`, `holds/hold-shelf.js:29`, `holds/holds.js:98`, `notifications/overdue-notices.js:19` call `notify()` | yes | A call order only one entry point follows (templates are `null` until started). Causes bug B2. | Bug B2 fixed **and** no file outside `notifications/` references `notifierReady`. |
| H6 | `members/membership.js:6` (`LOAN_LIMITS` keys), `admin/handlers.js:35` (`VALID_TIERS`) | yes | Tier names listed twice in two areas. | At most one file has an array of 3+ tier names or an object keyed by 3+ tier names. |
| H7 | `admin/handlers.js:119-138` `markItemLost`, re-exported as public API from the admin layer (`index.js:35`); writes `catalogStore._items`, `loanStore._loans`, `ledgerStore._entries` directly | yes | Lost-item handling (a circulation + fines feature) lives in the HTTP handler module and bypasses the owners. | `markItemLost` is defined outside admin/http/handler files, and no admin file touches store objects or `._loans/_entries/_items/_byId`. |
| H8 | `shared/dates.js:7` plus inline `/ 86400000` at `fines/fines.js:9`, `reports/overdue-report.js:15`, `notifications/overdue-notices.js:14` | yes | Day-difference arithmetic copied (there is a `daysBetween`). | At most one file contains the ms-per-day constant (any spelling). |
| H9 | `circulation/loans.js:110-125` and `holds/hold-shelf.js:18-35` | yes | Promoting the next hold (status, `readyUntil`, item status, notice) is implemented twice; the shelf-days rule is copied (`loans.js:115` vs `hold-shelf.js:10-14`, re-applied in `holds.js:94`). | At most one file assigns `readyUntil`. |
| H10 | `notifications/templates.js:6,10,14` and `notifications/preview.js:6-10` (`SAMPLES`) | no | Notice kinds listed twice; a new template without a sample previews with `undefined` fields. | At most one file names all three notice kinds. |

### Needless links

| Id | Where | Wide | What is wrong | Fixed when |
| --- | --- | --- | --- | --- |
| N1 | `reports/circulation-report.js:21,38`, `overdue-report.js:13,17`, `fines-report.js:18,21`, `exports.js:15`, `daily-summary.js:20,33` | yes | Reports reach into `loanStore._loans`, `memberStore._byId`, `ledgerStore._entries`. | No report-like file (path matches report/export/summary/digest/activity) references a store object or an underscore internal. |
| N2 | `shared/money.js:1` imports `../admin/settings.js` | yes | Stable shared formatting depends on the admin layer. | The file defining `formatCents` imports nothing from admin/http/handler paths. |
| N3 | `shared/dates.js:44` `formatDate(date, forNotice)`; only `notifications/overdue-notices.js:21` passes `true` | no | General function with a flag one caller understands. | No `forNotice`, and `formatDate` (if kept) has at most one parameter. |
| N4 | `circulation/loans.js:18` defines `LendError`; imported by `shared/validate.js:1`, `shared/calendar.js:5`, members, catalog, fines, holds, admin | yes | Shared code imports volatile circulation code just for the error type. | `class LendError` lives in a file that defines no checkout/return/renew, and no shared/util/lib file imports circulation. |
| N5 | `holds/hold-queue.js` (one-line wrappers over an array), used by `holds/holds.js:10`, `hold-shelf.js:6`, `circulation/loans.js:12`, `reports/hold-queue-report.js:4` | yes | Shallow module; callers in three areas lean on its array. | None of `pushToQueue/peekQueue/shiftQueue/queueLength` remain. |
| N6 | `members/member-store.js:1,79,90` imports `openLoansFor` from `circulation/loans.js`, which imports the member store; `LendError` adds more cycles | yes | Import cycles between members, catalog, fines, holds and circulation. | No import cycle among reachable files. |

### Surplus

| Id | Where | Wide | What is wrong | Fixed when |
| --- | --- | --- | --- | --- |
| S1 | `members/member-service.js:6-32` | no | Pass-through wrapper over the member store (7 of 9 functions only forward). | No reachable file other than `index.js` has 2+ exported functions that only forward their parameters to an imported function. |
| S2 | `config.js:3-10` `FEATURES` (`holdsV2: true`, `smsNotices: false`, `auditLog: false`), dead branches at `holds/holds.js:54-60`, `notifications/notifier.js:24`, `circulation/loans.js:92,107` | yes | Flags that never vary, with dead code (and a dead `channels/sms.js`). | None of the three flag names remain. |
| S3 | `catalog/marc-import.js` | no | Dead module, nothing imports it. Only fix is deleting it. | **Found-only**: REPORT.md names `marc-import`/Dynix. |
| S4 | `shared/dates.js:50` `plusDays`, `fines/fines.js:59` re-export of `FINE_PER_DAY, MAX_FINE_CENTS`, `catalog/item-types.js:9` `export default` | no | Re-exports nobody uses. | All three gone. |
| S5 | `circulation/loan-policy.js:14` `RENEWAL_MODE`, dead branch `circulation/loans.js:140` | no | Constant that never varies, with a dead branch. | No `RENEWAL_MODE` / `'from-due'`. |

### Special cases

| Id | Where | Wide | What is wrong | Fixed when |
| --- | --- | --- | --- | --- |
| SC1 | `circulation/loans.js:115`, `holds/hold-shelf.js:12` | yes | `=== 'harbor'` instead of a branch property (`shared/branches.js` already has per-branch data). Behaviour (10 days at Harbor) must stay. | No comparison against the literal `'harbor'`. |
| SC2 | `circulation/loans.js:111-124` | no | Swallowed error: a failure while moving a returned item to the hold shelf is only logged; it hides bug B2. | No catch block without `throw` or `return`. |
| SC3 | `admin/http.js:78,89` `await pause(5)` before `/search`; `catalog/search.js:28-33` rebuilds the index in a `setTimeout` | yes | A sleep papering over a deferred index (direct `searchCatalog` right after `addItem` is stale). | No `setTimeout`/`setImmediate`/`sleep(`/`pause(`/`delay(`. |
| SC4 | `tests/fines.test.js:41` `test.skip` | no | Disabled test; its assertion states the intended behaviour (bug B3). | No `.skip`/`.todo`/`{ skip }` in tests. |
| SC5 | `fines/fines.js:17-20` `if (member.tier === 'staff' / 'junior' / 'senior')` | yes | Tier rules as ifs on hard-coded names while tiers already have a table in `members/membership.js`; one name is wrong (bug B5). | No comparison of a tier against a string literal (incl. `case`). |

### Comments and tests

| Id | Where | Fixed when |
| --- | --- | --- |
| C | 10 comments that restate the next line: `member-store.js:42`, `catalog-store.js:49,62`, `loans.js:79,105,142`, `holds.js:55`, `notifier.js:25`, `overdue-report.js:12`, `fines-report.js:41` | At most 1 of the 10 left in reachable code. |
| TT | 5 tests that cannot fail or recompute the implementation: `dates.test.js:27` (expects `addDays(...)`, the implementation itself), `members.test.js:33` (`assert.ok(true)`), `circulation.test.js:72` (`deepEqual(listLoans(), listLoans())`), `fines.test.js:48` (recomputes `formatCents`), `holds.test.js:57-62` (assertion inside an empty `catch`) | None of the 5 patterns left in `tests/`. |

## Bugs (5)

Each is reachable through the public API, has a `BUG ` golden key, and is scored on behaviour.
"Reported" = fixed **and** REPORT.md matches the keyword.

| Id | Where | Golden key: pristine → fixed | Why unambiguous | Reported keyword |
| --- | --- | --- | --- | --- |
| B1 | `admin/handlers.js:34` `ALLOWED_TYPES` lacks `'audiobook'` | `BUG http add audiobook`: 400 BAD_TYPE → 201 | README lists audiobook as an item type with a 14-day loan and 50c fine; `addItem` accepts it; `LOAN_DAYS` and `FINE_PER_DAY` have it; it is a copy of `ITEM_TYPES` missing an entry its source has. | `audiobook` |
| B2 | `notifications/notifier.js:6,20,35`; init only in `admin/http.js:82`; swallowed at `circulation/loans.js:122` | `BUG overdue notices without startNotifications`: `{error: TypeError}` → one notice sent. `BUG hold-ready notice without startNotifications`: hold marked ready and item moved to the shelf but no notice → notice sent | A public function (`sendOverdueNotices`) throws a raw `TypeError: Cannot read properties of null`; `returnItem` half-completes (hold ready, item on the shelf, member never told), contradicting README ("...the first member in the queue, who is notified"). The same calls work through `handleRequest`, which initialises first; nothing documents an init step, and `resetLibrary` silently undoes it. | `startNotifications`, notif…start/init, initiali[sz]e |
| B3 | `fines/fines.js:15` reads `item.replacementCents`; items store `replacementCostCents` | `BUG fine capped at replacement cost`: 2500 → 1200 | The comment on the line above, the README ("A fine never exceeds the item's replacement cost") and the skipped test `fines.test.js:41-45` (asserts 1200) all state the rule; the field name does not exist anywhere else. | `replacement` |
| B4 | `circulation/loans.js:133` `renewals > MAX_RENEWALS` | `BUG third renewal`: third renewal succeeds → any error (RENEWAL_LIMIT) | README: "at most twice"; the constant is `MAX_RENEWALS = 2`; the admin API refuses the third (`handlers.js:157`, `>=`). The two copies of the rule disagree and the doc says which is right. | `renew` |
| B5 | `fines/fines.js:18` `tier === 'junior'` | `BUG child pays half`: 100 → 50 | README: "Children's cards pay half". There is no `junior` tier (`membership.js`, `VALID_TIERS`; `registerMember` rejects it), so the branch is dead and children pay in full. | `child`/`junior` |

No non-bug golden key depends on a bug (bug scenarios are isolated with `resetLibrary()`, and no other
scenario has a child's fine, a fine above a replacement cost, a third renewal, an audiobook via HTTP,
or a notice without the notifier started). The reference fix confirms: all five fixed, zero
unexplained changes. So `allowedIfFixed` in `score.mjs` is empty.

## Traps (5): look like problems, must stay

| Id | Where | Why it must stay | Golden key(s) |
| --- | --- | --- | --- |
| T1 | `fines/payments.js:17-30`: retry once on `ETIMEDOUT` | Comment cites the payment vendor's support ticket (PW-4471): first request on an idle connection times out without charging; one retry with the same idempotency key is the vendor's advice. Declines must not be retried. Tested. | `TRAP payment retried once on a timeout`, `TRAP payment decline not retried`, `TRAP payment two timeouts` |
| T2 | `fines/fines.js:10-12`: one grace day, then the grace day is charged too | Looks like an off-by-one; it is stated policy (README, comment "circulation policy 4.2", test). | `TRAP grace day` |
| T3 | `fines/fines.js:19-20`: seniors pay `Math.floor(total * 2 / 3)` | Looks like a rounding to unify with `Math.round` elsewhere (`fines-report.js` average); README: board decision, rounded down in the member's favour. 100 → 66, 175 → 116. | `TRAP senior two thirds rounded down` |
| T4 | `catalog/barcodes.js:31` `parseBarcode`, exported at `index.js:29` | Nothing inside the repo calls it; README: the Selfserv kiosks call `parseBarcode`/`toBarcode`. Public API. | `TRAP kiosk barcodes` (+ export list) |
| T5 | `circulation/loans.js:53-56`: maps are never lent | A special case on a type name; README: maps are for use in the library only. Moving it to a type property is fine; the behaviour must stay. | `TRAP map is not loanable` |

None of these can be read as a bug: each is stated in the README or in a comment citing an external
source, and four are covered by tests.

## Runtime-only behaviours (5): not problems, must stay unchanged

No test covers them; only running the code shows them. Any change appears in
`unexplainedBehaviourChanges`.

| Id | Where | Behaviour | Golden key(s) |
| --- | --- | --- | --- |
| R1 | `notifications/templates.js:8` parsed by `reports/notice-digest.js:6` | The hold-ready wording ("is ready for pickup at X until YYYY-MM-DD.") is parsed back by `holdPickupDigest`; rewording a template (e.g. while merging templates with preview samples, H10) silently empties the digest. | `hold flow`, `main hold shelf expiry` |
| R2 | `admin/settings.js:3,5`, `config.js:12` | Env defaults use `\|\|` and `parseInt`: `LENDWELL_CURRENCY=''` → USD; unknown currency → `"NOK 1,234.56"`; `LENDWELL_ADMIN_TOKEN=''` → dev token; `LENDWELL_MAX_HOLDS` `'0'`/`'lots'` → 5, `'3 holds'` → 3. A switch to `??` or `Number()` changes them. | `env currency …`, `env max holds …`, `env admin token …` (child processes) |
| R3 | `reports/fines-report.js:6-9` `dollars()` | The finance CSV writes plain decimals (`4.00`) whatever `LENDWELL_CURRENCY` is; "deduplicating" it with `formatCents` breaks the finance import. | `reports`, `env currency EUR` |
| R4 | `reports/overdue-report.js:31` (stable sort), `circulation-report.js` `popularTitles`, `member-activity.js` | Ties keep store order: equal days overdue stay in checkout order; equal checkout counts in first-borrowed order; same-day events loans → holds → charges. A rewrite that sorts by id/name or iterates a different store changes them. | `overdue report order`, `reports`, `hold flow` |
| R5 | `shared/branches.js` key order, `circulation-report.js` `branchSummary`, `daily-summary.js` | Branch rows come out main, harbor, hill (object key order); the type rows of `circulationReport` follow `ITEM_TYPES` order. Re-keying the tables (H1/H2, SC1) must keep the order. | `reports`, `lost item`, `ITEM_TYPES` |

## Selfcheck

`bash _shared/selfcheck.sh` checks: (a) fixture tests pass with one skip, size 2,000-4,000 lines in
6+ areas, fixture deterministic; (b) pristine scores 0 fixed / 0 bugs / all traps / 0 unexplained;
(c1) fixing N2 + S4 is credited exactly; (c2) fixing B4 is credited without unexplained changes;
(c3) fixing B2 in the notifier credits B2 but not H5; (c4) adding `audiobook` to the admin copy fixes
B1 but not H1; (c5) removing the retry breaks T1; (c6) `Math.round` for seniors breaks T3; (c7) `??`
for the currency default and rewording the hold notice are unexplained changes; (c8) the reference
restructure passes its tests and scores 27/27, 5/5, 5/5, 0 unexplained, and "To delete" in REPORT.md
counts S3 as found; (c9) a broken public API gets no behaviour credit.

## Known limitations

- Structural checks are regex/AST-light. A fix that reaches the same goal by an unusual spelling can be
  missed (e.g. N5 checks the old helper names are gone; an agent that renames the shallow helpers
  without deepening the module would be credited). H2/H6 accept one keyed table per concept even if a
  second, non-keyed list survives.
- "Found" is keyword matching on REPORT.md; a report that mentions a keyword in passing gets credit.
- H5 requires B2 to be fixed: an agent that instead documents "call startNotifications() first" gets
  neither.
- Error messages are not compared (golden records `err.code`/`err.name` only); HTTP error bodies
  record only `error`. Rewording a message is not caught.
- The C item requires at least 9 of the 10 restating comments gone; other restating comments an agent
  removes are not scored.
