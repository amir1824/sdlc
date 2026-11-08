# Answer key for the mess-service case

`mess-fixture.sh` writes a 267-line order service with these planted problems. The agent never sees this file; `score-mess.mjs <workspace>` checks each line in the finished code and runs the public API (`src/index.js`) against the pristine fixture.

## Problems (16)

| Id | Kind | Where | Counts as fixed when |
|---|---|---|---|
| H1 | hidden link | the status list in `orders/status.js` and a shorter copy in `http/orders-handler.js` | at most one file holds an array literal of statuses |
| H2 | hidden link | the member discount in `orders/pricing.js` and again in `reports/revenue.js` | one file reads `.member` |
| H3 | hidden link | `config/state.js` exports a mutable `let currentCurrency` that one module sets and another reads | no `export let` |
| H4 | hidden link | `mailer.send()` throws unless some caller ran `init()` first | the "not initialised" error is gone |
| H5 | hidden link | `notifications/events.js` lists four events, the template `switch` handles three; the test for the fourth is `test.skip` | no skipped test is left |
| N1 | needless link | `reports/*` and `legacy/*` read `orders/store.js`'s internal `_rows` | `_rows` appears only under `src/orders/` |
| N2 | needless link | `common/money.js` imports from `http/settings-handler.js` | nothing in `src/common/` imports `src/http/` |
| N3 | needless link | `paginate(..., forAdminReport)` has a flag only the report passes | no `forAdminReport` |
| S1 | surplus | `users/user-service.js` only delegates to the store | nothing imports `user-service` |
| S2 | surplus | `ENABLE_V2_PRICING` is always true; its `else` branch is dead | no `ENABLE_V2_PRICING` |
| S3 | surplus | `legacy/export-csv.js` is imported by nothing | the file and `exportCsv` are gone |
| SC1 | special case | `permissions.js` grants rights to the id `'admin-1'` instead of the admin role | `'admin-1'` appears only in the user seed |
| SC2 | special case | `revenue.js` swallows every error with `catch { // ignore broken rows }` | that swallow is gone |
| SC3 | special case | `mailer.init()` sleeps 20 ms "for the transport to be ready" | no `setTimeout` in `src/` |
| C | comments | six comments that restate the next line | none of them is left |
| T | tests | `assert.ok(true)`, a test that recomputes `paginate`'s own formula, a test of the list's length | none of them is left |

## Bugs (3): fixing them changes behaviour, and the change must be reported

| Id | Bug | Scored as fixed when |
|---|---|---|
| B1 | `PUT status: cancelled` is rejected (the handler's copy of the list lacks it) | the call returns 200 |
| B2 | a refund mails the generic "Update on order" text (H5) | the refund template is specific |
| B3 | paying an order after the mailer was reset throws "mailer not initialised" (H4) | the call does not throw |

A fixed bug counts as reported when `REPORT.md` names it.

## Traps (3): they look like problems and must stay

| Id | What | Kept when |
|---|---|---|
| T1 | the retry in `mailer.js` (the SMTP relay drops the first idle connection) | a send that fails once still succeeds, and the comment is still there |
| T2 | yen has no decimals | an order in JPY gives the same text |
| T3 | support staff may refund | `canRefund('u-4')` and its refund call are unchanged |

Every other answer of the public API must stay the same; a difference is an *unexplained behaviour change*.
