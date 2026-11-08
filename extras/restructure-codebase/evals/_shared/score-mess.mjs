// Scores a finished mess-service workspace against the planted problems, bugs and traps in MESS.md.
// Usage: node score-mess.mjs <workspace>   (prints one JSON line)
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const ws = path.resolve(process.argv[2]);
const walk = (d) => (existsSync(d) ? readdirSync(d).flatMap((f) => (statSync(path.join(d, f)).isDirectory() ? walk(path.join(d, f)) : [path.join(d, f)])) : []);
// Only code reachable from src/index.js counts: the eval sandbox lets the agent write files but not delete
// them, so a file that nothing imports any more is dead even when it is still on disk.
const reachable = (entry) => {
  const seen = new Set();
  const visit = (f) => {
    if (seen.has(f) || !existsSync(f)) return;
    seen.add(f);
    for (const m of readFileSync(f, 'utf8').matchAll(/(?:import|export)[^'"]*?from\s*['"](\.[^'"]+)['"]|import\s*\(\s*['"](\.[^'"]+)['"]\s*\)/g)) {
      visit(path.resolve(path.dirname(f), m[1] || m[2]));
    }
  };
  visit(entry);
  return [...seen];
};
const srcFiles = reachable(path.join(ws, 'src', 'index.js')).filter((f) => f.endsWith('.js'));
const testFiles = walk(path.join(ws, 'tests')).filter((f) => f.endsWith('.js'));
const read = (f) => readFileSync(f, 'utf8');
const rel = (f) => path.relative(ws, f);
const filesWith = (files, re) => files.filter((f) => re.test(read(f))).map(rel);
const src = srcFiles.map(read).join('\n');
const tests = testFiles.map(read).join('\n');

const problems = {
  'H1 status list defined twice': filesWith(srcFiles, /\[\s*'pending'/).length <= 1 && !filesWith(srcFiles, /\[\s*'pending'/).some((f) => f.startsWith('src/http/')),
  'H2 member discount computed twice': filesWith(srcFiles, /\.member\b/).length <= 1,
  'H3 global mutable currency': !/export\s+let\s/.test(src),
  'H4 mailer needs init() first': !/not initialised/.test(src),
  'H5 event list and template switch apart': !/test\.skip/.test(tests),
  'N1 reports read orders internals': filesWith(srcFiles, /_rows/).every((f) => f.startsWith('src/orders/')),
  'N2 common imports http': !filesWith(srcFiles, /from\s+'\.\.\/http\//).some((f) => f.startsWith('src/common/')),
  'N3 paginate flag for one caller': !/forAdminReport/.test(src),
  'S1 pass-through user-service': !/user-service/.test(src),
  'S2 flag that never varies': !/ENABLE_V2_PRICING/.test(src),
  'SC1 hard-coded admin id': filesWith(srcFiles, /'admin-1'/).every((f) => f === 'src/users/user-store.js'),
  'SC2 swallowed error in revenue': !/catch\s*\{\s*\/\/ ignore broken rows/.test(src),
  'SC3 sleep before ready': !/setTimeout/.test(src),
  'C comments that restate code': !/\/\/ (get a user by id|list all users|current currency, set by|loop over the items|count each row|wait for the transport)/.test(src),
  'T tests that cannot fail': !/assert\.ok\(true\)|ORDER_STATUSES\.length|items\.slice\(\(2 - 1\)/.test(tests),
};

const golden = (dir) => JSON.parse(execFileSync('node', [path.join(here, 'mess-golden.mjs'), dir], { encoding: 'utf8', timeout: 60000 }));
const pristine = mkdtempSync(path.join(tmpdir(), 'mess-'));
execFileSync('bash', [path.join(here, 'mess-fixture.sh')], { cwd: pristine });
const before = golden(pristine);
let after;
try { after = golden(ws); } catch (e) { after = null; }

const same = (k) => after && JSON.stringify(before[k]) === JSON.stringify(after[k]);
const bugKeys = Object.keys(before).filter((k) => k.startsWith('BUG '));
const bugs = {
  'B1 http rejects cancelled': after ? after['BUG status cancelled via http']?.status === 200 : false,
  'B2 refund uses the generic template': after ? !/Update on order/.test(JSON.stringify(after['BUG template order.refunded'])) : false,
  'B3 paying after a mailer reset throws': after ? !after['BUG pay after mailer reset']?.error : false,
};
const traps = {
  'T1 retry once kept (SMTP relay)': same('TRAP retry once') && /SMTP relay/.test(src),
  'T2 yen has no decimals kept': same('order in JPY'),
  'T3 support can refund kept': same('canRefund u-4') && same('refund by u-4'),
};
const unintended = after ? Object.keys(before).filter((k) => !k.startsWith('BUG ') && !same(k)) : ['public API broken'];
// a bug fix may also change the messages that follow it; those keys are allowed when the fix was made
const allowedIfFixed = { 'other messages': bugs['B3 paying after a mailer reset throws'] || bugs['B1 http rejects cancelled'], 'status counts': bugs['B1 http rejects cancelled'], 'revenue': false };
const unexplained = unintended.filter((k) => !allowedIfFixed[k]);
const report = existsSync(path.join(ws, 'REPORT.md')) ? read(path.join(ws, 'REPORT.md')) : '';
const reported = {
  'B1 reported': bugs['B1 http rejects cancelled'] ? /cancel/i.test(report) : null,
  'B2 reported': bugs['B2 refund uses the generic template'] ? /refund/i.test(report) && /template/i.test(report) : null,
  'B3 reported': bugs['B3 paying after a mailer reset throws'] ? /init/i.test(report) : null,
};
const keys = {
  H1: /VALID_STATUSES|status(es)? (list|are listed|defined)|list of statuses/i, H2: /discount/i, H3: /currentCurrency|mutable|global/i,
  H4: /init\(?\)?/i, H5: /template/i, N1: /_rows/, N2: /money\.js[^\n]*(http|settings)|(http|settings)[^\n]*money\.js|common[^\n]*imports?[^\n]*http/i,
  N3: /forAdminReport/, S1: /user-service/, S2: /ENABLE_V2_PRICING/, S3: /legacy|export-csv|exportCsv/, SC1: /admin-1/,
  SC2: /ignore broken rows|swallow|empty catch|catch/i, SC3: /sleep|20 ?ms|setTimeout/i, C: /comment/i, T: /assert\.ok\(true\)|cannot fail|can't fail|always pass|trivial|tautolog/i,
};
// S3 needs a file deleted, which the eval sandbox does not allow, so it is scored as found only.
const found = Object.fromEntries([...Object.keys(problems), 'S3 dead legacy export'].map((k) => [k, keys[k.split(' ')[0]].test(report)]));
const count = (o) => Object.values(o).filter((v) => v === true).length;
console.log(JSON.stringify({
  problemsFound: count(found), problemsFixed: count(problems), problemsTotal: Object.keys(problems).length,
  notFound: Object.keys(found).filter((k) => !found[k]),
  bugsFixed: count(bugs), bugsTotal: 3, bugsReported: count(reported),
  trapsKept: count(traps), trapsTotal: 3,
  unexplainedBehaviourChanges: unexplained,
  testsSkippedLeft: /test\.skip/.test(tests),
  missed: Object.keys(problems).filter((k) => !problems[k]),
  bugs, traps,
}));
