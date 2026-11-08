// Drives the public API (src/index.js) of a lendwell workspace over fixed scenarios and prints the
// observable results as JSON. Usage: node golden.mjs <workspace>
// Keys starting with "BUG " are the planted bugs (expected to change when fixed); keys starting
// with "TRAP " must never change. Every scenario is wrapped, so a throw is recorded as {error}.
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const ws = path.resolve(process.argv[2] ?? '.');
const indexUrl = pathToFileURL(path.join(ws, 'src', 'index.js')).href;
const L = await import(indexUrl);
const out = {};
const errOf = (e) => ({ error: e?.code ?? e?.name ?? String(e) });
async function run(name, fn) {
  try {
    out[name] = await fn();
  } catch (e) {
    out[name] = errOf(e);
  }
}
const attempt = async (fn) => {
  try {
    return await fn();
  } catch (e) {
    return errOf(e);
  }
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const TOKEN = { authorization: 'Bearer dev-admin-token' };
const http = async (method, p, body) => {
  const res = await L.handleRequest({ method, path: p, headers: TOKEN, body });
  return res.status >= 400 ? { status: res.status, error: res.body?.error } : { status: res.status, body: res.body };
};
const dayAfter = (date, n) => {
  const [y, m, d] = date.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
};

const EXPECTED_EXPORTS = [
  'registerMember', 'getMember', 'findMember', 'listMembers', 'memberSummary', 'deactivateMember', 'changeTier',
  'updateContact', 'memberIdForCard', 'addItem', 'getItem', 'findItem', 'listItems', 'updateItem', 'withdrawItem',
  'ITEM_TYPES', 'searchCatalog', 'parseBarcode', 'toBarcode', 'LendError', 'checkoutItem', 'returnItem', 'renewLoan',
  'findLoan', 'listLoans', 'placeHold', 'cancelHold', 'listHolds', 'expireHolds', 'getBalance', 'listCharges',
  'waiveFine', 'payFine', 'memberStatement', 'statementText', 'markItemLost', 'startNotifications', 'sentMessages',
  'sendOverdueNotices', 'circulationReport', 'popularTitles', 'branchSummary', 'overdueReport', 'finesReport',
  'finesCsv', 'finesSummary', 'holdPickupDigest', 'memberActivity', 'holdQueueReport', 'loansCsv', 'dailySummary',
  'setClosedDates', 'listClosedDates', 'formatCents', 'handleRequest', 'resetLibrary',
];

function seed() {
  L.resetLibrary();
  L.registerMember({ name: 'Ada Okafor', email: 'ada@example.org' }); // m-0001 adult
  L.registerMember({ name: 'Ben Okafor', tier: 'child' }); // m-0002 child, no email
  L.registerMember({ name: 'Cleo Marsh', tier: 'senior', email: 'cleo@example.org', phone: '555-0101' }); // m-0003
  L.registerMember({ name: 'Dev Patel', tier: 'staff', homeBranch: 'harbor' }); // m-0004
  L.registerMember({ name: 'Eve Lund', email: 'eve@example.org', homeBranch: 'hill' }); // m-0005 adult
  L.addItem({ title: 'The Salt Road', author: 'Jane Halloran', type: 'book', year: 2011, replacementCostCents: 2400 }); // i-0001
  L.addItem({ title: 'Harbor Lights', type: 'dvd', branch: 'harbor', replacementCostCents: 1999 }); // i-0002
  L.addItem({ title: 'Tidewater Monthly', type: 'magazine', branch: 'hill', replacementCostCents: 600 }); // i-0003
  L.addItem({ title: 'The Salt Road (audio)', author: 'Jane Halloran', type: 'audiobook', replacementCostCents: 3500 }); // i-0004
  L.addItem({ title: 'County Survey 1910', type: 'map' }); // i-0005
  L.addItem({ title: 'A Field Guide to Gulls', author: 'R. Ferreira', type: 'book', branch: 'harbor' }); // i-0006
  L.addItem({ title: 'Salt and Stone', author: 'M. Idris', type: 'book', branch: 'hill' }); // i-0007
  L.addItem({ title: 'Night Ferry', type: 'dvd' }); // i-0008
}
// checks an item out on 2026-03-01 and returns it `late` days after its due date
function lateReturn(memberId, itemId, late) {
  const loan = L.checkoutItem(memberId, itemId, '2026-03-01');
  return L.returnItem(itemId, dayAfter(loan.dueOn, late)).fineCents;
}

await run('public API names present', () => EXPECTED_EXPORTS.filter((n) => !(n in L)));
await run('members', () => (seed(), L.listMembers()));
await run('register errors', async () => {
  seed();
  return {
    tier: await attempt(() => L.registerMember({ name: 'X', tier: 'gold' })),
    name: await attempt(() => L.registerMember({ name: '  ' })),
    email: await attempt(() => L.registerMember({ name: 'X', email: 'not-an-email' })),
    branch: await attempt(() => L.registerMember({ name: 'X', homeBranch: 'moon' })),
    next: L.registerMember({ name: 'Fay Ito' }).id,
  };
});
await run('member updates', async () => {
  seed();
  return {
    tier: L.changeTier('m-0001', 'senior'),
    contact: L.updateContact('m-0002', { email: 'BEN@example.org', phone: '555-0202' }),
    badTier: await attempt(() => L.changeTier('m-0001', 'junior')),
    find: L.findMember('m-0099') ?? null,
    get: await attempt(() => L.getMember('m-0099')),
  };
});
await run('cards', () => {
  seed();
  const card = L.getMember('m-0003').cardNumber;
  return {
    card,
    back: L.memberIdForCard(card),
    spaced: L.memberIdForCard(card.replace(/(\d{4})/g, '$1 ')),
    old: L.memberIdForCard('29380000000126'),
    typo: L.memberIdForCard(card.slice(0, 13) + ((Number(card[13]) + 1) % 10)),
    junk: L.memberIdForCard('hello'),
  };
});
await run('deactivate', async () => {
  seed();
  L.checkoutItem('m-0005', 'i-0001', '2026-03-01');
  const refused = await attempt(() => L.deactivateMember('m-0005'));
  L.returnItem('i-0001', '2026-03-05');
  const closed = L.deactivateMember('m-0005');
  return { refused, closed, summary: L.memberSummary('m-0005'), borrow: await attempt(() => L.checkoutItem('m-0005', 'i-0007', '2026-03-06')) };
});
await run('items', () => (seed(), L.listItems()));
await run('ITEM_TYPES', () => [...L.ITEM_TYPES]);
await run('item updates', async () => {
  seed();
  return {
    update: L.updateItem('i-0001', { title: 'The Salt Road (2nd ed.)', replacementCostCents: 2600 }),
    bad: await attempt(() => L.updateItem('i-0001', { status: 'lost' })),
    withdraw: L.withdrawItem('i-0008'),
    again: await attempt(() => L.withdrawItem('i-0008')),
    borrowWithdrawn: await attempt(() => L.checkoutItem('m-0001', 'i-0008', '2026-03-01')),
    addBadType: await attempt(() => L.addItem({ title: 'Vinyl', type: 'record' })),
    addAudiobook: L.addItem({ title: 'Gulls, Read Aloud', type: 'audiobook', branch: 'hill' }),
  };
});
await run('checkout each type', () => {
  seed();
  return ['i-0001', 'i-0002', 'i-0003', 'i-0004'].map((id) => L.checkoutItem('m-0001', id, '2026-03-01'));
});
await run('TRAP map is not loanable', async () => (seed(), attempt(() => L.checkoutItem('m-0001', 'i-0005', '2026-03-01'))));
await run('closed dates', async () => {
  seed();
  const set = L.setClosedDates(['2026-03-23', '2026-03-22', '2026-03-08', '2026-03-22']);
  return {
    set,
    list: L.listClosedDates(),
    book: L.checkoutItem('m-0001', 'i-0001', '2026-03-01').dueOn,
    dvd: L.checkoutItem('m-0001', 'i-0002', '2026-03-01').dueOn,
    bad: await attempt(() => L.setClosedDates(['2026-02-30'])),
  };
});
await run('checkout errors', async () => {
  seed();
  L.checkoutItem('m-0001', 'i-0001', '2026-03-01');
  return {
    twice: await attempt(() => L.checkoutItem('m-0005', 'i-0001', '2026-03-02')),
    noMember: await attempt(() => L.checkoutItem('m-0099', 'i-0002', '2026-03-02')),
    noItem: await attempt(() => L.checkoutItem('m-0001', 'i-0099', '2026-03-02')),
    badDate: await attempt(() => L.checkoutItem('m-0001', 'i-0002', '03/02/2026')),
    returnNotOut: await attempt(() => L.returnItem('i-0002', '2026-03-02')),
    returnBeforeCheckout: await attempt(() => L.returnItem('i-0001', '2026-02-27')),
  };
});
await run('loan limit child', async () => {
  seed();
  const extra = [1, 2, 3, 4, 5].map((n) => L.addItem({ title: `Picture Book ${n}`, type: 'book' }).id);
  for (const id of extra.slice(0, 5)) L.checkoutItem('m-0002', id, '2026-03-01');
  return { sixth: await attempt(() => L.checkoutItem('m-0002', 'i-0001', '2026-03-01')), summary: L.memberSummary('m-0002') };
});
await run('TRAP grace day', () => {
  seed();
  return [lateReturn('m-0001', 'i-0001', 1), lateReturn('m-0001', 'i-0001', 2), lateReturn('m-0001', 'i-0001', 3), lateReturn('m-0001', 'i-0001', 0)];
});
await run('fines by type', () => {
  seed();
  return {
    dvd3: lateReturn('m-0001', 'i-0002', 3),
    magazine5: lateReturn('m-0001', 'i-0003', 5),
    audiobook2: lateReturn('m-0001', 'i-0004', 2),
    balance: L.getBalance('m-0001'),
    charges: L.listCharges('m-0001'),
  };
});
await run('TRAP senior two thirds rounded down', () => {
  seed();
  return [lateReturn('m-0003', 'i-0001', 4), lateReturn('m-0003', 'i-0002', 3), lateReturn('m-0003', 'i-0001', 7), lateReturn('m-0003', 'i-0003', 5)];
});
await run('staff pay no fines', () => (seed(), [lateReturn('m-0004', 'i-0002', 9), lateReturn('m-0004', 'i-0001', 30)]));
await run('BUG child pays half', () => (seed(), lateReturn('m-0002', 'i-0001', 4)));
await run('BUG fine capped at replacement cost', () => {
  seed();
  const cheap = L.addItem({ title: 'Pocket Atlas of Birds', type: 'book', replacementCostCents: 1200 });
  return lateReturn('m-0001', cheap.id, 100);
});
await run('blocked over ten dollars', async () => {
  seed();
  const fine = lateReturn('m-0001', 'i-0002', 11);
  const blocked = await attempt(() => L.checkoutItem('m-0001', 'i-0001', '2026-04-01'));
  const waived = L.waiveFine('m-0001', 200, { reason: 'first offence', on: '2026-04-01' });
  const overWaive = await attempt(() => L.waiveFine('m-0001', 5000, { reason: 'x' }));
  const noReason = await attempt(() => L.waiveFine('m-0001', 100, {}));
  return { fine, blocked, waived, overWaive, noReason, balance: L.getBalance('m-0001'), after: L.checkoutItem('m-0001', 'i-0001', '2026-04-01').dueOn };
});
await run('renewals', () => {
  seed();
  L.checkoutItem('m-0001', 'i-0001', '2026-03-01');
  return [L.renewLoan('i-0001', '2026-03-10'), L.renewLoan('i-0001', '2026-03-20'), L.findLoan('i-0001')];
});
await run('BUG third renewal', async () => {
  seed();
  L.checkoutItem('m-0001', 'i-0001', '2026-03-01');
  L.renewLoan('i-0001', '2026-03-10');
  L.renewLoan('i-0001', '2026-03-20');
  return attempt(() => L.renewLoan('i-0001', '2026-03-30'));
});
await run('third renewal via http', async () => {
  seed();
  L.checkoutItem('m-0001', 'i-0001', '2026-03-01');
  const r = [];
  for (const on of ['2026-03-10', '2026-03-20', '2026-03-30']) r.push(await http('POST', '/renewals', { itemId: 'i-0001', on }));
  return r;
});
await run('renewal with a waiting hold', async () => {
  seed();
  L.checkoutItem('m-0001', 'i-0001', '2026-03-01');
  L.placeHold('m-0005', 'i-0001', '2026-03-02');
  return attempt(() => L.renewLoan('i-0001', '2026-03-05'));
});
await run('hold flow', async () => {
  seed();
  L.startNotifications();
  L.checkoutItem('m-0001', 'i-0001', '2026-03-01');
  const placed = [L.placeHold('m-0005', 'i-0001', '2026-03-02'), L.placeHold('m-0003', 'i-0001', '2026-03-03')];
  const returned = L.returnItem('i-0001', '2026-03-10');
  const afterReturn = { holds: L.listHolds({ itemId: 'i-0001' }), status: L.getItem('i-0001').status };
  const wrongMember = await attempt(() => L.checkoutItem('m-0003', 'i-0001', '2026-03-11'));
  const collected = L.checkoutItem('m-0005', 'i-0001', '2026-03-11');
  L.returnItem('i-0001', '2026-03-20');
  return {
    placed, returned, afterReturn, wrongMember, collected,
    holds: L.listHolds(),
    messages: L.sentMessages(),
    digest: L.holdPickupDigest(),
    activity: L.memberActivity('m-0005'),
    queueReport: L.holdQueueReport('2026-03-20', { minimum: 0 }).filter((r) => r.waiting > 0 || r.itemId === 'i-0001'),
  };
});
await run('BUG hold-ready notice without startNotifications', () => {
  seed();
  L.checkoutItem('m-0001', 'i-0001', '2026-03-01');
  L.placeHold('m-0005', 'i-0001', '2026-03-02');
  L.returnItem('i-0001', '2026-03-10');
  return { kinds: L.sentMessages().map((m) => m.kind), hold: L.listHolds()[0].status, item: L.getItem('i-0001').status };
});
await run('BUG overdue notices without startNotifications', () => {
  seed();
  L.checkoutItem('m-0001', 'i-0002', '2026-03-01');
  return L.sendOverdueNotices('2026-03-09');
});
await run('overdue notices', () => {
  seed();
  L.startNotifications();
  L.checkoutItem('m-0001', 'i-0002', '2026-03-01'); // due 03-08
  L.checkoutItem('m-0003', 'i-0008', '2026-03-02'); // due 03-09
  L.checkoutItem('m-0005', 'i-0001', '2026-02-01'); // due 02-22
  L.checkoutItem('m-0002', 'i-0003', '2026-03-06'); // due 03-13
  return { first: L.sendOverdueNotices('2026-03-15'), second: L.sendOverdueNotices('2026-03-16'), messages: L.sentMessages() };
});
await run('harbor hold shelf', () => {
  seed();
  L.startNotifications();
  L.checkoutItem('m-0004', 'i-0006', '2026-03-01');
  L.placeHold('m-0005', 'i-0006', '2026-03-02');
  L.placeHold('m-0001', 'i-0006', '2026-03-03');
  L.returnItem('i-0006', '2026-03-05');
  const ready = L.listHolds({ itemId: 'i-0006' });
  const lastDay = L.expireHolds('2026-03-15');
  const dayAfterLast = L.expireHolds('2026-03-16');
  return { ready, lastDay, dayAfterLast, holds: L.listHolds({ itemId: 'i-0006' }), status: L.getItem('i-0006').status, kinds: L.sentMessages().map((m) => [m.kind, m.memberId, m.channel]) };
});
await run('main hold shelf expiry', () => {
  seed();
  L.startNotifications();
  L.checkoutItem('m-0001', 'i-0008', '2026-03-01');
  L.placeHold('m-0005', 'i-0008', '2026-03-02');
  L.returnItem('i-0008', '2026-03-04');
  return { until: L.listHolds()[0].readyUntil, d11: L.expireHolds('2026-03-11'), d12: L.expireHolds('2026-03-12'), status: L.getItem('i-0008').status, digest: L.holdPickupDigest() };
});
await run('cancel a ready hold', () => {
  seed();
  L.startNotifications();
  L.checkoutItem('m-0001', 'i-0007', '2026-03-01');
  const first = L.placeHold('m-0005', 'i-0007', '2026-03-02');
  L.placeHold('m-0003', 'i-0007', '2026-03-02');
  L.returnItem('i-0007', '2026-03-06');
  const cancelled = L.cancelHold(first.id, '2026-03-07');
  return { cancelled, holds: L.listHolds({ itemId: 'i-0007' }), status: L.getItem('i-0007').status, messages: L.sentMessages().length };
});
await run('hold errors', async () => {
  seed();
  L.checkoutItem('m-0001', 'i-0001', '2026-03-01');
  const h = L.placeHold('m-0005', 'i-0001', '2026-03-02');
  return {
    available: await attempt(() => L.placeHold('m-0005', 'i-0002', '2026-03-02')),
    own: await attempt(() => L.placeHold('m-0001', 'i-0001', '2026-03-02')),
    duplicate: await attempt(() => L.placeHold('m-0005', 'i-0001', '2026-03-03')),
    noHold: await attempt(() => L.cancelHold('h-0099', '2026-03-03')),
    cancel: L.cancelHold(h.id, '2026-03-03'),
    again: await attempt(() => L.cancelHold(h.id, '2026-03-04')),
  };
});
await run('hold limit', async () => {
  seed();
  const ids = [1, 2, 3, 4, 5, 6].map((n) => L.addItem({ title: `Popular Novel ${n}`, type: 'book' }).id);
  for (const id of ids) L.checkoutItem('m-0005', id, '2026-03-01');
  const placed = [];
  for (const id of ids) placed.push(await attempt(() => L.placeHold('m-0001', id, '2026-03-02').position));
  return placed;
});
const flaky = (failures) => {
  let calls = 0;
  return {
    get calls() { return calls; },
    async charge(req) {
      calls += 1;
      const f = failures[calls - 1];
      if (f) throw Object.assign(new Error(f), { code: f });
      return { chargeId: `pw-${calls}-${req.amountCents}` };
    },
  };
};
await run('TRAP payment retried once on a timeout', async () => {
  seed();
  lateReturn('m-0001', 'i-0002', 4);
  const gw = flaky(['ETIMEDOUT']);
  const paid = await L.payFine('m-0001', 150, { gateway: gw, on: '2026-03-20' });
  return { paid, calls: gw.calls, balance: L.getBalance('m-0001') };
});
await run('TRAP payment decline not retried', async () => {
  seed();
  lateReturn('m-0001', 'i-0002', 4);
  const gw = flaky(['CARD_DECLINED']);
  return { result: await attempt(() => L.payFine('m-0001', 150, { gateway: gw })), calls: gw.calls, balance: L.getBalance('m-0001') };
});
await run('TRAP payment two timeouts', async () => {
  seed();
  lateReturn('m-0001', 'i-0002', 4);
  const gw = flaky(['ETIMEDOUT', 'ETIMEDOUT']);
  return { result: await attempt(() => L.payFine('m-0001', 150, { gateway: gw })), calls: gw.calls, balance: L.getBalance('m-0001') };
});
await run('pay fine offline', async () => {
  seed();
  lateReturn('m-0001', 'i-0002', 4);
  return {
    over: await attempt(() => L.payFine('m-0001', 1000)),
    zero: await attempt(() => L.payFine('m-0001', 0)),
    paid: await L.payFine('m-0001', 400, { on: '2026-03-20' }),
    nothing: await attempt(() => L.payFine('m-0001', 1)),
    noMember: await attempt(() => L.payFine('m-0099', 1)),
  };
});
await run('lost item', async () => {
  seed();
  L.checkoutItem('m-0001', 'i-0001', '2026-03-01');
  const lost = L.markItemLost('i-0001', '2026-04-15');
  return {
    lost,
    again: await attempt(() => L.markItemLost('i-0001', '2026-04-16')),
    balance: L.getBalance('m-0001'),
    item: L.getItem('i-0001').status,
    loans: L.listLoans({ memberId: 'm-0001' }),
    activity: L.memberActivity('m-0001'),
    daily: L.dailySummary('2026-04-15'),
    summary: L.branchSummary(),
  };
});
await run('reports', async () => {
  seed();
  // a month of desk activity, no child fines and nothing near a replacement cost
  L.checkoutItem('m-0001', 'i-0001', '2026-03-01');
  L.checkoutItem('m-0003', 'i-0002', '2026-03-01');
  L.checkoutItem('m-0005', 'i-0003', '2026-03-02');
  L.checkoutItem('m-0001', 'i-0008', '2026-03-02');
  L.returnItem('i-0002', '2026-03-12'); // cleo, 4 days late
  L.returnItem('i-0003', '2026-03-09'); // on time
  L.checkoutItem('m-0005', 'i-0002', '2026-03-12');
  L.returnItem('i-0008', '2026-03-14'); // ada, 5 days late
  L.checkoutItem('m-0004', 'i-0003', '2026-03-14');
  L.checkoutItem('m-0005', 'i-0007', '2026-03-03');
  L.checkoutItem('m-0003', 'i-0006', '2026-03-03');
  L.checkoutItem('m-0005', 'i-0004', '2026-03-14');
  L.returnItem('i-0004', '2026-03-31'); // eve, 3 days late
  return {
    circulation: L.circulationReport({ from: '2026-03-01', to: '2026-03-31' }),
    popular: L.popularTitles({ from: '2026-03-01', to: '2026-03-31', limit: 4 }),
    branches: L.branchSummary(),
    overdue: L.overdueReport('2026-03-26'),
    fines: L.finesReport(),
    csv: L.finesCsv(),
    finesSummary: L.finesSummary(),
    loansCsv: L.loansCsv({ from: '2026-03-02', to: '2026-03-14' }),
    daily: L.dailySummary('2026-03-14'),
    statement: L.memberStatement('m-0001', { from: '2026-03-01', to: '2026-03-31' }),
    statementText: L.statementText(L.memberStatement('m-0003', { from: '2026-03-13', to: '2026-03-31' })),
    activity: L.memberActivity('m-0005'),
    badRange: await attempt(() => L.circulationReport({ from: '2026-03-01' })),
  };
});
await run('overdue report order', () => {
  seed();
  // equal days overdue must keep checkout order: Eve (checked out first), then Cleo, then Ada
  L.checkoutItem('m-0005', 'i-0002', '2026-03-01');
  L.checkoutItem('m-0003', 'i-0008', '2026-03-01');
  L.checkoutItem('m-0001', 'i-0003', '2026-03-01');
  L.checkoutItem('m-0001', 'i-0001', '2026-02-10');
  return L.overdueReport('2026-03-20').map((r) => [r.memberName, r.title, r.daysOverdue, r.fineSoFar]);
});
await run('search', async () => {
  seed();
  await sleep(20);
  L.checkoutItem('m-0001', 'i-0007', '2026-03-01');
  L.withdrawItem('i-0008');
  await sleep(20);
  const ids = (rows) => rows.map((r) => r.id);
  return {
    salt: ids(L.searchCatalog('salt')),
    saltRoad: ids(L.searchCatalog('Salt ROAD')),
    halloran: ids(L.searchCatalog('halloran', { type: 'audiobook' })),
    available: ids(L.searchCatalog('salt', { availableOnly: true })),
    branch: ids(L.searchCatalog('salt', { branch: 'hill' })),
    withdrawn: ids(L.searchCatalog('ferry')),
    empty: L.searchCatalog('  '),
  };
});
await run('TRAP kiosk barcodes', () => {
  const code = L.toBarcode('i-0001');
  return {
    code,
    big: L.toBarcode('i-12345'),
    back: L.parseBarcode(code),
    scanner: L.parseBarcode(` ${code.toLowerCase()}\n`),
    misread: L.parseBarcode(code.slice(0, 9) + ((Number(code[9]) + 1) % 10)),
    other: L.parseBarcode('9781234567897'),
    nothing: L.parseBarcode(''),
  };
});
await run('formatCents', () => [0, 5, 99, 1250, -1250, 100000, 123456789].map((c) => L.formatCents(c)));
await run('formatCents rejects fractions', async () => attempt(() => L.formatCents(12.5)));
await run('http auth', async () => [
  (await L.handleRequest({ method: 'GET', path: '/members' })).status,
  (await L.handleRequest({ method: 'GET', path: '/members', headers: { authorization: 'Bearer wrong' } })).status,
  (await L.handleRequest({ method: 'GET', path: '/members', headers: { Authorization: 'Bearer dev-admin-token' } })).status,
]);
await run('http members', async () => {
  L.resetLibrary();
  const made = await http('POST', '/members', { name: 'Ada Okafor', email: 'ada@example.org' });
  await http('POST', '/members', { name: 'Ben Okafor', tier: 'child' });
  return {
    made,
    badTier: await http('POST', '/members', { name: 'X', tier: 'gold' }),
    list: await http('GET', '/members?page=1'),
    byName: await http('GET', '/members?name=ben'),
    one: await http('GET', '/members/m-0001'),
    card: await http('GET', `/cards/${made.body.cardNumber}`),
    badCard: await http('GET', '/cards/123'),
    missing: await http('GET', '/members/m-0042'),
    tier: await http('PATCH', '/members/m-0002/tier', { tier: 'adult' }),
    close: await http('DELETE', '/members/m-0002'),
  };
});
await run('BUG http add audiobook', async () => {
  L.resetLibrary();
  return http('POST', '/items', { title: 'The Salt Road (audio)', type: 'audiobook' });
});
await run('http items', async () => {
  L.resetLibrary();
  return {
    book: await http('POST', '/items', { title: 'The Salt Road', type: 'book', replacementCostCents: 2400 }),
    map: await http('POST', '/items', { title: 'County Survey 1910', type: 'map' }),
    bad: await http('POST', '/items', { title: 'Vinyl', type: 'record' }),
    get: await http('GET', '/items/i-0001'),
    patch: await http('PATCH', '/items/i-0001', { author: 'Jane Halloran' }),
    withdraw: await http('DELETE', '/items/i-0002'),
    missing: await http('GET', '/items/i-0404'),
    search: await http('GET', '/search?q=salt'),
  };
});
await run('http circulation', async () => {
  seed();
  return {
    out: await http('POST', '/checkouts', { memberId: 'm-0001', itemId: 'i-0002', on: '2026-03-01' }),
    map: await http('POST', '/checkouts', { memberId: 'm-0001', itemId: 'i-0005', on: '2026-03-01' }),
    hold: await http('POST', '/holds', { memberId: 'm-0005', itemId: 'i-0002', on: '2026-03-02' }),
    holds: await http('GET', '/holds?itemId=i-0002'),
    back: await http('POST', '/returns', { itemId: 'i-0002', on: '2026-03-12' }),
    item: await http('GET', '/items/i-0002'),
    charges: await http('GET', '/members/m-0001/charges'),
    waive: await http('POST', '/members/m-0001/waivers', { amountCents: 100, reason: 'flood at Harbor', on: '2026-03-12' }),
    statement: await http('GET', '/members/m-0001/statement?from=2026-03-01&to=2026-03-31&format=text'),
    collect: await http('POST', '/checkouts', { memberId: 'm-0005', itemId: 'i-0002', on: '2026-03-13' }),
    lost: await http('POST', '/items/i-0002/lost', { on: '2026-05-01' }),
    cancelMissing: await http('DELETE', '/holds/h-0042?on=2026-03-13'),
    expire: await http('POST', '/holds/expire', { on: '2026-03-20' }),
    messages: L.sentMessages(),
  };
});
await run('http reports and notices', async () => {
  seed();
  L.checkoutItem('m-0001', 'i-0002', '2026-03-01');
  L.checkoutItem('m-0003', 'i-0001', '2026-02-01');
  L.returnItem('i-0001', '2026-02-26');
  return {
    notices: await http('POST', '/notices/overdue', { on: '2026-03-15' }),
    overdue: await http('GET', '/reports/overdue?on=2026-03-15'),
    circulation: await http('GET', '/reports/circulation?from=2026-02-01&to=2026-03-31'),
    fines: await http('GET', '/reports/fines'),
    csv: await http('GET', '/reports/fines.csv'),
    holds: await http('GET', '/reports/holds?on=2026-03-15'),
    loans: await http('GET', '/reports/loans.csv?from=2026-02-01&to=2026-03-31'),
    daily: await http('GET', '/reports/daily?on=2026-02-26'),
    preview: await http('GET', '/notices/preview/loan.overdue'),
    previewReady: await http('GET', '/notices/preview/hold.ready'),
    previewMissing: await http('GET', '/notices/preview/fine.paid'),
    messages: L.sentMessages(),
  };
});
await run('http calendar and routing', async () => {
  L.resetLibrary();
  return {
    put: await http('PUT', '/calendar', { closedDates: ['2026-12-25', '2026-12-24'] }),
    get: await http('GET', '/calendar'),
    bad: await http('PUT', '/calendar', { closedDates: 'tomorrow' }),
    unknown: await http('GET', '/nowhere'),
    wrongVerb: await http('PUT', '/members'),
    trailingSlash: (await http('GET', '/calendar/')).status,
  };
});

// Settings read from the environment at start-up: each case runs in a fresh process.
const envCase = (env, code) => {
  const script = `const L = await import(${JSON.stringify(indexUrl)});\n${code}`;
  const clean = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith('LENDWELL_')));
  try {
    const text = execFileSync(process.execPath, ['--input-type=module', '-e', script], { cwd: ws, env: { ...clean, ...env }, encoding: 'utf8', timeout: 20000, stdio: ['ignore', 'pipe', 'pipe'] });
    return JSON.parse(text.trim().split('\n').pop());
  } catch (e) {
    return { error: 'process failed' };
  }
};
const money = `
L.resetLibrary();
const m = L.registerMember({ name: 'Ada Okafor' });
const i = L.addItem({ title: 'Harbor Lights', type: 'dvd' });
const loan = L.checkoutItem(m.id, i.id, '2026-03-01');
L.returnItem(i.id, '2026-03-12');
console.log(JSON.stringify({ fmt: [L.formatCents(123456), L.formatCents(-5)], csv: L.finesCsv(), report: L.finesReport(), overdue: L.finesSummary().total }));`;
const holdsCode = `
L.resetLibrary();
const owner = L.registerMember({ name: 'Eve Lund' });
const ada = L.registerMember({ name: 'Ada Okafor' });
const r = [];
for (let n = 1; n <= 7; n += 1) {
  const it = L.addItem({ title: 'Novel ' + n, type: 'book' });
  L.checkoutItem(owner.id, it.id, '2026-03-01');
  try { r.push(L.placeHold(ada.id, it.id, '2026-03-02').position); } catch (e) { r.push(e.code); }
}
console.log(JSON.stringify(r));`;
const tokenCode = `
const s = async (t) => (await L.handleRequest({ method: 'GET', path: '/calendar', headers: { authorization: 'Bearer ' + t } })).status;
console.log(JSON.stringify([await s('dev-admin-token'), await s('s3cret')]));`;
await run('env currency EUR', () => envCase({ LENDWELL_CURRENCY: 'EUR' }, money));
await run('env currency empty falls back to USD', () => envCase({ LENDWELL_CURRENCY: '' }, money));
await run('env currency without a symbol', () => envCase({ LENDWELL_CURRENCY: 'NOK' }, money));
await run('env max holds 2', () => envCase({ LENDWELL_MAX_HOLDS: '2' }, holdsCode));
await run('env max holds 0 falls back', () => envCase({ LENDWELL_MAX_HOLDS: '0' }, holdsCode));
await run('env max holds not a number', () => envCase({ LENDWELL_MAX_HOLDS: 'lots' }, holdsCode));
await run('env max holds 3 with suffix', () => envCase({ LENDWELL_MAX_HOLDS: '3 holds' }, holdsCode));
await run('env admin token', () => envCase({ LENDWELL_ADMIN_TOKEN: 's3cret' }, tokenCode));
await run('env admin token empty', () => envCase({ LENDWELL_ADMIN_TOKEN: '' }, tokenCode));

console.log(JSON.stringify(out, null, 1));
