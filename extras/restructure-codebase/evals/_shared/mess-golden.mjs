// Prints what the orders service's public API (src/index.js) does over fixed scenarios, as JSON.
// Usage: node mess-golden.mjs <workspace>
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const api = await import(pathToFileURL(path.join(path.resolve(process.argv[2]), 'src', 'index.js')).href);
const out = {};
const run = async (key, fn) => {
  try { out[key] = await fn(); } catch (e) { out[key] = { error: String(e && e.message) }; }
};
const items = (c, q = 1) => [{ priceCents: c, qty: q }];
const fresh = () => { api.resetOrders(); api.resetMailer(); };

fresh();
await run('create member', () => api.handleCreateOrder({ body: { userId: 'u-2', items: items(1234, 3) } }));
await run('create customer', () => api.handleCreateOrder({ body: { userId: 'u-3', items: items(999, 2) } }));
await run('create unknown user', () => api.handleCreateOrder({ body: { userId: 'nobody', items: items(500) } }));
await run('create no items', () => api.handleCreateOrder({ body: { userId: 'u-3', items: [] } }));
await run('create items not array', () => api.handleCreateOrder({ body: { userId: 'u-3' } }));
await run('status paid', () => api.handleSetStatus({ params: { id: 'o-1' }, body: { status: 'paid' } }));
await run('status shipped', () => api.handleSetStatus({ params: { id: 'o-1' }, body: { status: 'shipped' } }));
await run('status pending', () => api.handleSetStatus({ params: { id: 'o-2' }, body: { status: 'pending' } }));
await run('status bogus', () => api.handleSetStatus({ params: { id: 'o-2' }, body: { status: 'lost' } }));
await run('status missing order', () => api.handleSetStatus({ params: { id: 'o-99' }, body: { status: 'paid' } }));
await run('OPEN status cancelled via http', () => api.handleSetStatus({ params: { id: 'o-3' }, body: { status: 'cancelled' } }));
for (const u of ['u-3', 'u-4', 'admin-1', 'nobody']) {
  await run(`refund by ${u}`, () => api.handleRefund({ user: u, params: { id: 'o-2' } }));
}
await run('refund missing order', () => api.handleRefund({ user: 'u-4', params: { id: 'o-99' } }));
await run('BUG refund message', () => api.sentMessages().filter((m) => m.event === 'order.refunded').map((m) => m.text));
await run('other messages', () => api.sentMessages().filter((m) => m.event !== 'order.refunded'));
await run('status counts', () => api.statusCounts());
await run('revenue', () => api.revenueCents());
for (let i = 0; i < 9; i++) await api.handleCreateOrder({ body: { userId: i % 2 ? 'u-2' : 'u-3', items: items(100 * (i + 1)) } });
await run('report page 1', () => api.ordersPage(1));
await run('report page 3', () => api.ordersPage(3));
await run('list page 1', () => api.handleListOrders({ query: {} }));
await run('list page 2', () => api.handleListOrders({ query: { page: '2' } }));
for (const u of ['admin-1', 'u-2', 'u-3', 'u-4', 'nobody']) {
  await run(`canRefund ${u}`, () => api.canRefund(u));
  await run(`canViewReports ${u}`, () => api.canViewReports(u));
}
for (const c of ['JPY', 'EUR', 'GBP', 'USD']) {
  await run(`currency ${c}`, () => api.handleSetCurrency({ body: { currency: c } }));
  await run(`order in ${c}`, () => api.handleCreateOrder({ body: { userId: 'u-2', items: items(1235, 1) } }).then((r) => r.body.total));
}
for (const e of ['order.created', 'order.paid', 'order.shipped', 'nope']) await run(`template ${e}`, () => api.templateFor(e));
await run('BUG template order.refunded', () => api.templateFor('order.refunded'));
let calls = 0;
await run('TRAP retry once', () => api.sendNotification('order.paid', 'o-1', async (m) => { calls += 1; if (calls === 1) throw new Error('relay idle'); return m; }));
await run('send always failing', () => api.sendNotification('order.paid', 'o-1', async () => { throw new Error('down'); }));
fresh();
await api.handleCreateOrder({ body: { userId: 'u-3', items: items(100) } });
api.resetMailer();
await run('BUG pay after mailer reset', () => api.handleSetStatus({ params: { id: 'o-1' }, body: { status: 'paid' } }));
console.log(JSON.stringify(out));
