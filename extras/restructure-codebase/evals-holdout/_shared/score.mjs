// Scores a finished holdout-service (lendwell) workspace against the answer key in KEY.md.
// Usage: node score.mjs <workspace>   (prints one JSON line)
//
// Structure is judged from the code only, and only on files reachable from src/index.js through
// static imports: the eval sandbox lets the agent create and edit files but not delete them, so a
// file nothing imports any more counts as gone. A problem whose only fix is deleting a file is
// scored as found-only (named in REPORT.md). Behaviour is judged by running golden.mjs on the
// workspace and on a freshly built pristine fixture.
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, readdirSync, existsSync, statSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const ws = path.resolve(process.argv[2] ?? '.');
const read = (f) => readFileSync(f, 'utf8');
const rel = (f) => path.relative(ws, f).split(path.sep).join('/');
const walk = (d) =>
  existsSync(d) ? readdirSync(d).flatMap((f) => (statSync(path.join(d, f)).isDirectory() ? walk(path.join(d, f)) : [path.join(d, f)])) : [];

// ---- reachable source ------------------------------------------------------------------------
const IMPORT_RE = /(?:import|export)\s[^'"`;]*?from\s*['"](\.{1,2}\/[^'"]+)['"]|import\s*['"](\.{1,2}\/[^'"]+)['"]|import\s*\(\s*['"](\.{1,2}\/[^'"]+)['"]\s*\)/g;
const resolveImport = (from, spec) => {
  const base = path.resolve(path.dirname(from), spec);
  for (const c of [base, `${base}.js`, `${base}.mjs`, path.join(base, 'index.js')]) if (existsSync(c) && statSync(c).isFile()) return c;
  return null;
};
const graph = new Map();
const visit = (f) => {
  if (graph.has(f)) return;
  const deps = [];
  graph.set(f, deps);
  for (const m of read(f).matchAll(IMPORT_RE)) {
    const target = resolveImport(f, m[1] || m[2] || m[3]);
    if (target) deps.push(target);
  }
  for (const d of deps) visit(d);
};
const entry = path.join(ws, 'src', 'index.js');
if (existsSync(entry)) visit(entry);
const srcFiles = [...graph.keys()].filter((f) => /\.m?js$/.test(f));
const testFiles = walk(path.join(ws, 'tests')).filter((f) => /\.m?js$/.test(f));

const stripComments = (t) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1');
const code = new Map(srcFiles.map((f) => [f, stripComments(read(f))]));
const raw = new Map(srcFiles.map((f) => [f, read(f)]));
const allCode = [...code.values()].join('\n');
const tests = testFiles.map(read).join('\n');
const filesWhere = (pred) => srcFiles.filter((f) => pred(code.get(f), f)).map(rel);
const none = (re) => !re.test(allCode);

// ---- helpers -----------------------------------------------------------------------------------
const TYPES = ['book', 'dvd', 'magazine', 'audiobook', 'map'];
const TIERS = ['adult', 'child', 'senior', 'staff'];
const quoted = (text, name) => new RegExp(`['"\`]${name}['"\`]`).test(text);
const arrayListing = (text, names, min = 3) =>
  [...text.matchAll(/\[[^\[\]]*\]/g)].some((m) => names.filter((n) => quoted(m[0], n)).length >= min);
const keyedTable = (text, names, min = 3) =>
  names.filter((n) => new RegExp(`(^|[\\s{,])['"]?${n}['"]?\\s*:(?!:)`, 'm').test(text)).length >= min;
// a binding imported from another module and read as a value (not called as a getter)
const readsImportedBinding = (name) =>
  srcFiles.some((f) => {
    const t = code.get(f);
    if (!new RegExp(`import\\s*\\{[^}]*\\b${name}\\b[^}]*\\}\\s*from`).test(t)) return false;
    const body = t.replace(/import\s*\{[^}]*\}\s*from\s*['"][^'"]+['"];?/g, '');
    return new RegExp(`\\b${name}\\b(?!\\s*\\()`).test(body);
  });
const exportedLets = () => srcFiles.flatMap((f) => [...code.get(f).matchAll(/export\s+(?:let|var)\s+(\w+)/g)].map((m) => m[1]));
const definers = (name) => {
  const direct = filesWhere((t) => new RegExp(`function\\s+${name}\\b|\\b${name}\\s*=\\s*(async\\s*)?(function|\\(|\\w+\\s*=>)`).test(t));
  if (direct.length) return direct;
  const alias = allCode.match(new RegExp(`(\\w+)\\s+as\\s+${name}\\b`));
  return alias && alias[1] !== name ? definers(alias[1]) : [];
};
const catchBodies = (text) => {
  const bodies = [];
  for (const m of text.matchAll(/\bcatch\s*(\([^)]*\))?\s*\{/g)) {
    let depth = 1;
    let i = m.index + m[0].length;
    const start = i;
    while (i < text.length && depth > 0) {
      if (text[i] === '{') depth += 1;
      else if (text[i] === '}') depth -= 1;
      i += 1;
    }
    bodies.push(text.slice(start, i - 1));
  }
  return bodies;
};
const hasCycle = () => {
  const state = new Map();
  const dfs = (f) => {
    state.set(f, 1);
    for (const d of graph.get(f) ?? []) {
      if (state.get(d) === 1) return true;
      if (!state.has(d) && dfs(d)) return true;
    }
    state.set(f, 2);
    return false;
  };
  return [...graph.keys()].some((f) => !state.has(f) && dfs(f));
};
// An exported function whose whole body forwards its own parameters, unchanged, to a function
// imported from another module.
const importedNames = (t) => {
  const names = new Set();
  const namespaces = new Set();
  for (const m of t.matchAll(/import\s+([^'"]*?)\s+from\s*['"][^'"]+['"]/g)) {
    const clause = m[1];
    const ns = clause.match(/\*\s+as\s+(\w+)/);
    if (ns) namespaces.add(ns[1]);
    const braces = clause.match(/\{([^}]*)\}/);
    if (braces) for (const part of braces[1].split(',')) { const name = part.trim().split(/\s+as\s+/).pop(); if (name) names.add(name); }
    const def = clause.match(/^\s*(\w+)\s*(,|$)/);
    if (def) names.add(def[1]);
  }
  return { names, namespaces };
};
const passThroughCount = (t) => {
  const { names, namespaces } = importedNames(t);
  const isImported = (callee) => (callee.includes('.') ? namespaces.has(callee.split('.')[0]) : names.has(callee));
  const forwards = [
    ...t.matchAll(/export\s+(?:async\s+)?function\s+\w+\s*\(([^)]*)\)\s*\{\s*return\s+(?:await\s+)?([\w.]+)\(\s*\1\s*\)\s*;?\s*\}/g),
    ...t.matchAll(/export\s+const\s+\w+\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*([\w.]+)\(\s*\1\s*\)\s*;/g),
  ];
  return forwards.filter((m) => isImported(m[2])).length;
};

// ---- behaviour ---------------------------------------------------------------------------------
const cleanEnv = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith('LENDWELL_')));
const golden = (dir) => JSON.parse(execFileSync(process.execPath, [path.join(here, 'golden.mjs'), dir], { encoding: 'utf8', timeout: 120000, env: cleanEnv, stdio: ['ignore', 'pipe', 'pipe'] }));
const pristine = mkdtempSync(path.join(tmpdir(), 'lendwell-pristine-'));
execFileSync('bash', [path.join(here, 'fixture.sh')], { cwd: pristine, stdio: 'ignore' });
const before = golden(pristine);
rmSync(pristine, { recursive: true, force: true });
let after = null;
try {
  after = golden(ws);
} catch {
  after = null;
}
const same = (k) => after !== null && JSON.stringify(before[k]) === JSON.stringify(after[k]);

const bugs = {
  'B1 admin API rejects audiobooks': after?.['BUG http add audiobook']?.status === 201,
  'B2 notices crash or vanish unless startNotifications ran':
    Array.isArray(after?.['BUG hold-ready notice without startNotifications']?.kinds) &&
    after['BUG hold-ready notice without startNotifications'].kinds.includes('hold.ready') &&
    Array.isArray(after?.['BUG overdue notices without startNotifications']) &&
    after['BUG overdue notices without startNotifications'].length === 1,
  'B3 fine cap ignores the replacement cost': after?.['BUG fine capped at replacement cost'] === 1200,
  'B4 renewLoan allows a third renewal': typeof after?.['BUG third renewal']?.error === 'string',
  'B5 children pay full fines': after?.['BUG child pays half'] === 50,
};

// ---- structure (from code) ---------------------------------------------------------------------
const outsideNotifications = srcFiles.filter((f) => !/notif/i.test(rel(f)));
const adminFiles = srcFiles.filter((f) => /admin|http|handler|route/i.test(rel(f)));
const reportFiles = srcFiles.filter((f) => /report|export|summary|digest|activity/i.test(rel(f)));
const lendErrorHomes = filesWhere((t) => /class\s+LendError\b/.test(t));
const formatCentsHomes = definers('formatCents');
const lostHomes = definers('markItemLost');
const formatDateParams = srcFiles.flatMap((f) => [...code.get(f).matchAll(/function\s+formatDate\s*\(([^)]*)\)/g)].map((m) => m[1].split(',').filter((p) => p.trim()).length));

// the stores' private fields, and the store objects that expose them
const INTERNALS = /\._(loans|entries|items|byId)\b|\b(loanStore|memberStore|ledgerStore|catalogStore)\b/;

const RESTATING = [
  'return the member', 'add the item to the map', 'check if the item exists', 'create the loan id', 'set status to available',
  'increment the renewal count', 'push the hold onto the queue', 'push the message to the outbox', 'loop over all loans', 'sum the balances',
];
const restatingLeft = RESTATING.filter((c) => srcFiles.some((f) => new RegExp(`//\\s*${c}\\s*$`, 'im').test(raw.get(f))));
const WEAK_TESTS = [
  /dueDateFor\(\s*'2026-03-01',\s*21\s*\),\s*addDays\(\s*'2026-03-01',\s*21\s*\)/,
  /assert\.ok\(\s*true\s*\)/,
  /listLoans\(\)\s*,\s*listLoans\(\)/,
  /\(1250\s*\/\s*100\)\.toFixed\(2\)/,
  /catch\s*(\(\w*\))?\s*\{\s*(\/\/[^\n]*\s*|\/\*[\s\S]*?\*\/\s*)*\}/,
];

const problems = {
  'H1 item-type list copied (catalog, admin, reports)': filesWhere((t) => arrayListing(t, TYPES)).length <= 1,
  'H2 per-type loan days and fine rates in separate tables': filesWhere((t) => keyedTable(t, TYPES)).length <= 1,
  'H3 closedDates exported as a live mutable binding': !exportedLets().some((n) => /closed|holiday|calendar/i.test(n)) && !readsImportedBinding('closedDates'),
  'H4 outbox exported as a live mutable binding': !exportedLets().some((n) => /outbox|sent|message/i.test(n)) && !readsImportedBinding('outbox'),
  'H5 notices need startNotifications() first; only the admin API calls it':
    bugs['B2 notices crash or vanish unless startNotifications ran'] && !outsideNotifications.some((f) => /\bnotifierReady\b/.test(code.get(f))),
  'H6 tier names listed in members and admin': filesWhere((t) => arrayListing(t, TIERS) || keyedTable(t, TIERS)).length <= 1,
  'H7 lost-item feature lives in the admin layer': lostHomes.length > 0 && lostHomes.every((f) => !/admin|http|handler|route/i.test(f)) && !adminFiles.some((f) => INTERNALS.test(code.get(f))),
  'H8 day-difference arithmetic copied': filesWhere((t) => /86400000|864e5|86_400_000|24\s*\*\s*60\s*\*\s*60\s*\*\s*1000|1000\s*\*\s*60\s*\*\s*60\s*\*\s*24/.test(t)).length <= 1,
  'H9 hold-shelf promotion implemented twice': filesWhere((t) => /\breadyUntil\s*=(?!=)/.test(t)).length <= 1,
  'H10 notice kinds listed in templates and preview samples': filesWhere((t) => ['hold.ready', 'hold.expired', 'loan.overdue'].every((k) => quoted(t, k.replace('.', '\\.')))).length <= 1,
  'N1 reports read other modules\' internals': !reportFiles.some((f) => INTERNALS.test(code.get(f))),
  'N2 money formatting imports admin settings': formatCentsHomes.length > 0 && formatCentsHomes.every((f) => !/from\s*['"][^'"]*(admin|http|handler)[^'"]*['"]/.test(code.get(path.join(ws, f)))),
  'N3 formatDate flag only notices understand': none(/\bforNotice\b/) && formatDateParams.every((n) => n <= 1),
  'N4 LendError defined in circulation and imported by shared code':
    lendErrorHomes.length > 0 &&
    lendErrorHomes.every((f) => !/function\s+(checkoutItem|returnItem|renewLoan)\b/.test(code.get(path.join(ws, f)))) &&
    !srcFiles.some((f) => /shared|util|common|lib|core/i.test(rel(f)) && /from\s*['"][^'"]*(circulation|loans)[^'"]*['"]/.test(code.get(f))),
  'N5 shallow hold-queue module': none(/\b(pushToQueue|peekQueue|shiftQueue|queueLength)\b/),
  'N6 import cycles (members <-> circulation, LendError)': !hasCycle(),
  'S1 pass-through member-service': !srcFiles.some((f) => rel(f) !== 'src/index.js' && passThroughCount(code.get(f)) >= 2),
  'S2 FEATURES flags that never vary': none(/\b(holdsV2|smsNotices|auditLog)\b/),
  'S4 re-exports nobody uses': none(/\bplusDays\b/) && none(/export\s*\{[^}]*\b(FINE_PER_DAY|MAX_FINE_CENTS)\b[^}]*\}\s*from/) && none(/export\s+default\s+ITEM_TYPES/),
  'S5 RENEWAL_MODE constant with a dead branch': none(/\bRENEWAL_MODE\b|['"]from-due['"]/),
  'SC1 harbor special-cased by name (twice)': none(/[!=]==?\s*['"]harbor['"]|['"]harbor['"]\s*[!=]==?|case\s+['"]harbor['"]/),
  'SC2 swallowed error when moving a return to the hold shelf': !srcFiles.some((f) => catchBodies(code.get(f)).some((b) => !/\bthrow\b|\breturn\b/.test(b))),
  'SC3 sleep before search papers over the deferred index': none(/\bsetTimeout\b|\bsetImmediate\b|\b(sleep|pause|delay)\s*\(/),
  'SC4 disabled test': !/\.(skip|todo)\s*\(|\{\s*(skip|todo)\s*:/.test(tests),
  'SC5 tier fine rules as ifs on tier names': none(/\btier\s*[!=]==?\s*['"]|['"](adult|child|senior|staff|junior)['"]\s*[!=]==?\s*[\w.]*tier\b|case\s+['"](adult|child|senior|staff|junior)['"]/),
  'C comments that restate the next line': restatingLeft.length <= 1,
  'TT tests that cannot fail or recompute the implementation': WEAK_TESTS.every((re) => !re.test(tests)),
};

// ---- REPORT.md -----------------------------------------------------------------------------------
const reportPath = path.join(ws, 'REPORT.md');
const report = existsSync(reportPath) ? read(reportPath) : '';
const KEYWORDS = {
  H1: /ALLOWED_TYPES|TYPE_ORDER|item[- ]types?\b[^\n]*(list|cop|duplicat|twice|three)|(list|cop|duplicat)[^\n]*item[- ]types?/i,
  H2: /LOAN_DAYS[^\n]*FINE_PER_DAY|FINE_PER_DAY[^\n]*LOAN_DAYS|per[- ]type[^\n]*(table|map)/i,
  H3: /closedDates|export let[^\n]*closed|closed[- ]dates?[^\n]*(mutable|live binding|global)/i,
  H4: /outbox/i,
  H5: /startNotifications|notifierReady|templates? (is |are )?null|not (been )?started/i,
  H6: /VALID_TIERS|tier (names|list)[^\n]*(cop|duplicat|twice)|(cop|duplicat)[^\n]*tiers?/i,
  H7: /markItemLost/i,
  H8: /86400000|day[- ](difference|math|arithmetic)|days? between|daysBetween|daysLate|daysOverdue[^\n]*(cop|duplicat|inline)/i,
  H9: /readyUntil|releaseFromShelf|hold[- ]shelf[^\n]*(twice|duplicat|cop)|promot\w*[^\n]*(twice|duplicat|cop)/i,
  H10: /SAMPLES|preview\.js|preview[^\n]*(sample|template|kinds?)/i,
  N1: /_loans|_byId|_entries|_items|internals/i,
  N2: /money\.js[^\n]*(admin|settings)|(admin|settings)[^\n]*money\.js|formatCents[^\n]*(admin|settings)|CURRENCY[^\n]*(admin|settings)/i,
  N3: /forNotice|formatDate/i,
  N4: /LendError/i,
  N5: /hold-queue|pushToQueue|peekQueue|shiftQueue|queueLength|shallow/i,
  N6: /cycl|circular/i,
  S1: /member-service|pass[- ]?through/i,
  S2: /holdsV2|smsNotices|auditLog|FEATURES/i,
  S3: /marc-import|importDynixExport|Dynix/i,
  S4: /plusDays|re-?export/i,
  S5: /RENEWAL_MODE|from-due/i,
  SC1: /harbor/i,
  SC2: /swallow|could not finish moving|empty catch|catch[^\n]*(log|warn)/i,
  SC3: /setTimeout|pause\(|sleep|scheduleReindex|deferred (index|rebuild)/i,
  SC4: /test\.skip|skipped test|disabled test/i,
  SC5: /junior|tier ===|hard-?coded tier|tier[^\n]*\bif\b/i,
  C: /comment/i,
  TT: /assert\.ok\(true\)|cannot fail|can't fail|always pass|tautolog|recomput|listLoans\(\), listLoans\(\)/i,
};
const found = Object.fromEntries(
  [...Object.keys(problems), 'S3 dead Dynix import module (marc-import.js)'].map((k) => [k, KEYWORDS[k.split(' ')[0]].test(report)]),
);
const reportedKeys = {
  B1: /audiobook/i,
  B2: /startNotifications|notif\w*[^\n]*(start|init)|initiali[sz]/i,
  B3: /replacement/i,
  B4: /renew/i,
  B5: /child|junior/i,
};
const bugsReported = Object.fromEntries(Object.keys(bugs).map((k) => [k, bugs[k] ? reportedKeys[k.split(' ')[0]].test(report) : null]));

const traps = {
  'T1 Paywell timeout retried exactly once': ['TRAP payment retried once on a timeout', 'TRAP payment decline not retried', 'TRAP payment two timeouts'].every(same),
  'T2 grace day charged once past it': same('TRAP grace day'),
  'T3 seniors pay two thirds rounded down': same('TRAP senior two thirds rounded down'),
  'T4 parseBarcode stays public for the kiosks': same('TRAP kiosk barcodes') && same('public API names present'),
  'T5 maps are not loanable': same('TRAP map is not loanable'),
};

const changed = after ? Object.keys(before).filter((k) => !k.startsWith('BUG ') && !same(k)) : ['public API broken (golden run failed)'];
// A bug fix can only move the keys listed here; none of the non-bug scenarios depend on a bug.
const allowedIfFixed = {};
const unexplained = changed.filter((k) => !(allowedIfFixed[k] && allowedIfFixed[k]()));
const count = (o) => Object.values(o).filter((v) => v === true).length;

console.log(
  JSON.stringify({
    problemsFixed: count(problems),
    problemsTotal: Object.keys(problems).length,
    problemsFound: count(found),
    problemsFoundTotal: Object.keys(found).length,
    bugsFixed: count(bugs),
    bugsTotal: Object.keys(bugs).length,
    bugsReported: count(bugsReported),
    trapsKept: count(traps),
    trapsTotal: Object.keys(traps).length,
    unexplainedBehaviourChanges: unexplained,
    reachableSrcFiles: srcFiles.length,
    restatingCommentsLeft: restatingLeft.length,
    missed: Object.keys(problems).filter((k) => !problems[k]),
    notFound: Object.keys(found).filter((k) => !found[k]),
    problems,
    found,
    bugs,
    bugsReported,
    traps,
  }),
);
