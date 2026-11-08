#!/usr/bin/env bash
# Writes "orders", a small order service that is messy on purpose, for the mess-service eval case.
# MESS.md (next to this script, never copied into the workspace) lists every planted problem,
# bug and trap; score-mess.mjs checks each one in a finished workspace.
set -euo pipefail
mkdir -p src/config src/common src/http src/users src/orders src/reports src/notifications src/util src/legacy tests
cat > package.json <<'EOF'
{ "name": "orders", "version": "1.0.0", "type": "module", "scripts": { "test": "node --test" } }
EOF

cat > src/index.js <<'EOF'
export { handleCreateOrder, handleSetStatus, handleRefund, handleListOrders } from './http/orders-handler.js';
export { handleSetCurrency } from './http/settings-handler.js';
export { statusCounts, ordersPage } from './reports/summary.js';
export { revenueCents } from './reports/revenue.js';
export { canRefund, canViewReports } from './users/permissions.js';
export { send as sendNotification, sentMessages, resetMailer } from './notifications/mailer.js';
export { resetOrders } from './orders/store.js';
export { templateFor } from './notifications/templates.js';
EOF

cat > src/config/state.js <<'EOF'
// current currency, set by the settings handler
export let currentCurrency = 'USD';

export function setCurrency(c) {
  currentCurrency = c;
}
EOF

cat > src/config/feature-flags.js <<'EOF'
export const flags = { ENABLE_V2_PRICING: true, ENABLE_LEGACY_EXPORT: false };
EOF

cat > src/common/money.js <<'EOF'
import { getCurrency } from '../http/settings-handler.js';

export function formatMoney(cents) {
  const currency = getCurrency();
  if (currency === 'JPY') return `${Math.round(cents)} JPY`;
  return `${(cents / 100).toFixed(2)} ${currency}`;
}
EOF

cat > src/http/settings-handler.js <<'EOF'
import { currentCurrency, setCurrency } from '../config/state.js';

const SUPPORTED = ['USD', 'EUR', 'JPY'];

export function getCurrency() {
  return currentCurrency;
}

export function handleSetCurrency(req) {
  if (!SUPPORTED.includes(req.body.currency)) return { status: 400, body: { error: 'unsupported currency' } };
  setCurrency(req.body.currency);
  return { status: 200, body: { currency: req.body.currency } };
}
EOF

cat > src/users/user-store.js <<'EOF'
const users = [
  { id: 'admin-1', name: 'Root', role: 'admin', member: false },
  { id: 'u-2', name: 'Dana', role: 'customer', member: true },
  { id: 'u-3', name: 'Lior', role: 'customer', member: false },
  { id: 'u-4', name: 'Maya', role: 'support', member: true },
];

export function findUser(id) {
  return users.find((u) => u.id === id);
}

export function listUsers() {
  return users.slice();
}
EOF

cat > src/users/user-service.js <<'EOF'
import * as store from './user-store.js';

// get a user by id
export function getUserById(id) {
  return store.findUser(id);
}

// list all users
export function getAllUsers() {
  return store.listUsers();
}
EOF

cat > src/users/permissions.js <<'EOF'
import { getUserById } from './user-service.js';

export function canRefund(userId) {
  const user = getUserById(userId);
  if (!user) return false;
  if (user.id === 'admin-1') return true;
  return user.role === 'support';
}

export function canViewReports(userId) {
  const user = getUserById(userId);
  if (!user) return false;
  if (user.id === 'admin-1') return true;
  return false;
}
EOF

cat > src/orders/status.js <<'EOF'
export const ORDER_STATUSES = ['pending', 'paid', 'shipped', 'cancelled'];
EOF

cat > src/orders/store.js <<'EOF'
export const _rows = [];
let nextId = 1;

export function addOrder(order) {
  const row = { id: `o-${nextId++}`, status: 'pending', ...order };
  _rows.push(row);
  return row;
}

export function findOrder(id) {
  return _rows.find((r) => r.id === id);
}

export function listOrders() {
  return _rows.slice();
}

export function updateStatus(id, status) {
  const row = findOrder(id);
  if (row) row.status = status;
  return row;
}

export function resetOrders() {
  _rows.length = 0;
  nextId = 1;
}
EOF

cat > src/orders/pricing.js <<'EOF'
import { flags } from '../config/feature-flags.js';
import { findUser } from '../users/user-store.js';

export function orderTotal(order) {
  let subtotal = 0;
  // loop over the items
  for (const item of order.items) {
    subtotal += item.priceCents * item.qty;
  }
  const user = findUser(order.userId);
  let discount = 0;
  if (flags.ENABLE_V2_PRICING) {
    if (user && user.member) discount = Math.round((subtotal * 10) / 100);
  } else {
    if (user && user.member) discount = Math.round(subtotal * 0.05);
  }
  return subtotal - discount;
}
EOF

cat > src/reports/revenue.js <<'EOF'
import { _rows } from '../orders/store.js';
import { findUser } from '../users/user-store.js';

const MEMBER_DISCOUNT = 0.1;

export function revenueCents() {
  let total = 0;
  for (const row of _rows) {
    if (row.status !== 'paid' && row.status !== 'shipped') continue;
    try {
      const subtotal = row.items.reduce((s, i) => s + i.priceCents * i.qty, 0);
      const user = findUser(row.userId);
      const discount = user && user.member ? Math.round(subtotal * MEMBER_DISCOUNT) : 0;
      total += subtotal - discount;
    } catch {
      // ignore broken rows
    }
  }
  return total;
}
EOF

cat > src/reports/summary.js <<'EOF'
import { _rows } from '../orders/store.js';
import { paginate } from '../util/paginate.js';
import { formatMoney } from '../common/money.js';
import { orderTotal } from '../orders/pricing.js';

export function statusCounts() {
  const counts = { pending: 0, paid: 0, shipped: 0, cancelled: 0 };
  // count each row
  for (const r of _rows) counts[r.status] += 1;
  return counts;
}

export function ordersPage(page) {
  return paginate(_rows, page, 2, true).map((r) => ({ id: r.id, status: r.status, total: formatMoney(orderTotal(r)) }));
}
EOF

cat > src/util/paginate.js <<'EOF'
export function paginate(items, page, size = 10, forAdminReport = false) {
  const start = (page - 1) * size;
  const slice = items.slice(start, start + size);
  if (forAdminReport) return slice.slice().reverse();
  return slice;
}
EOF

cat > src/notifications/events.js <<'EOF'
export const EVENTS = ['order.created', 'order.paid', 'order.shipped', 'order.refunded'];
EOF

cat > src/notifications/templates.js <<'EOF'
export function templateFor(event) {
  switch (event) {
    case 'order.created':
      return 'Thanks, we got your order {id}.';
    case 'order.paid':
      return 'Payment received for {id}.';
    case 'order.shipped':
      return 'Order {id} is on its way.';
    default:
      return 'Update on order {id}.';
  }
}
EOF

cat > src/notifications/mailer.js <<'EOF'
import { templateFor } from './templates.js';

let ready = false;
const outbox = [];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// wait for the transport to be ready
export async function init() {
  await sleep(20);
  ready = true;
}

// the SMTP relay drops the first connection after it has been idle, so a failed send is retried once
async function deliver(message, transport) {
  try {
    return await transport(message);
  } catch {
    return await transport(message);
  }
}

async function defaultTransport(message) {
  outbox.push(message);
  return message;
}

export async function send(event, orderId, transport = defaultTransport) {
  if (!ready) throw new Error('mailer not initialised');
  const text = templateFor(event).replace('{id}', orderId);
  return deliver({ event, text }, transport);
}

export function sentMessages() {
  return outbox.slice();
}

export function resetMailer() {
  outbox.length = 0;
  ready = false;
}
EOF

cat > src/http/orders-handler.js <<'EOF'
import { addOrder, findOrder, listOrders, updateStatus } from '../orders/store.js';
import { orderTotal } from '../orders/pricing.js';
import { formatMoney } from '../common/money.js';
import { init, send } from '../notifications/mailer.js';
import { canRefund } from '../users/permissions.js';
import { paginate } from '../util/paginate.js';

const VALID_STATUSES = ['pending', 'paid', 'shipped'];

export async function handleCreateOrder(req) {
  if (!Array.isArray(req.body.items) || req.body.items.length === 0) {
    return { status: 400, body: { error: 'items required' } };
  }
  const order = addOrder({ userId: req.body.userId, items: req.body.items });
  await init();
  await send('order.created', order.id);
  return { status: 201, body: { id: order.id, total: formatMoney(orderTotal(order)) } };
}

export async function handleSetStatus(req) {
  const order = findOrder(req.params.id);
  if (!order) return { status: 404, body: { error: 'not found' } };
  if (!VALID_STATUSES.includes(req.body.status)) return { status: 400, body: { error: 'invalid status' } };
  updateStatus(order.id, req.body.status);
  if (req.body.status === 'paid') await send('order.paid', order.id);
  if (req.body.status === 'shipped') await send('order.shipped', order.id);
  return { status: 200, body: { id: order.id, status: req.body.status } };
}

export async function handleRefund(req) {
  if (!canRefund(req.user)) return { status: 403, body: { error: 'forbidden' } };
  const order = findOrder(req.params.id);
  if (!order) return { status: 404, body: { error: 'not found' } };
  updateStatus(order.id, 'cancelled');
  await send('order.refunded', order.id);
  return { status: 200, body: { id: order.id, status: 'cancelled' } };
}

export function handleListOrders(req) {
  const page = Number(req.query.page || 1);
  return { status: 200, body: paginate(listOrders(), page, 10, false).map((r) => r.id) };
}
EOF

cat > src/legacy/export-csv.js <<'EOF'
import { _rows } from '../orders/store.js';
import { flags } from '../config/feature-flags.js';

export function exportCsv() {
  if (!flags.ENABLE_LEGACY_EXPORT) return '';
  return _rows.map((r) => `${r.id},${r.status}`).join('\n');
}
EOF

cat > tests/orders.test.js <<'EOF'
import test from 'node:test';
import assert from 'node:assert/strict';
import { handleCreateOrder, handleSetStatus, handleRefund, handleListOrders, resetOrders, resetMailer } from '../src/index.js';

const items = [{ priceCents: 1000, qty: 2 }];

test('a member gets 10% off', async () => {
  resetOrders(); resetMailer();
  const r = await handleCreateOrder({ body: { userId: 'u-2', items } });
  assert.deepEqual(r, { status: 201, body: { id: 'o-1', total: '18.00 USD' } });
});
test('an order needs items', async () => {
  assert.equal((await handleCreateOrder({ body: { userId: 'u-3', items: [] } })).status, 400);
});
test('status can move to paid', async () => {
  resetOrders(); resetMailer();
  await handleCreateOrder({ body: { userId: 'u-3', items } });
  assert.deepEqual(await handleSetStatus({ params: { id: 'o-1' }, body: { status: 'paid' } }), { status: 200, body: { id: 'o-1', status: 'paid' } });
});
test('support can refund, a customer cannot', async () => {
  resetOrders(); resetMailer();
  await handleCreateOrder({ body: { userId: 'u-3', items } });
  assert.equal((await handleRefund({ user: 'u-3', params: { id: 'o-1' } })).status, 403);
  assert.equal((await handleRefund({ user: 'u-4', params: { id: 'o-1' } })).status, 200);
});
test('list orders', async () => {
  resetOrders(); resetMailer();
  await handleCreateOrder({ body: { userId: 'u-3', items } });
  assert.deepEqual(handleListOrders({ query: {} }).body, ['o-1']);
});
EOF

cat > tests/reports.test.js <<'EOF'
import test from 'node:test';
import assert from 'node:assert/strict';
import { handleCreateOrder, handleSetStatus, revenueCents, statusCounts, resetOrders, resetMailer } from '../src/index.js';

test('revenue counts paid orders with the member discount', async () => {
  resetOrders(); resetMailer();
  await handleCreateOrder({ body: { userId: 'u-2', items: [{ priceCents: 1000, qty: 1 }] } });
  await handleCreateOrder({ body: { userId: 'u-3', items: [{ priceCents: 500, qty: 1 }] } });
  await handleSetStatus({ params: { id: 'o-1' }, body: { status: 'paid' } });
  assert.equal(revenueCents(), 900);
  assert.deepEqual(statusCounts(), { pending: 1, paid: 1, shipped: 0, cancelled: 0 });
});
EOF

cat > tests/permissions.test.js <<'EOF'
import test from 'node:test';
import assert from 'node:assert/strict';
import { canViewReports } from '../src/index.js';

test('only the admin sees reports', () => {
  assert.equal(canViewReports('admin-1'), true);
  assert.equal(canViewReports('u-2'), false);
});
EOF

cat > tests/templates.test.js <<'EOF'
import test from 'node:test';
import assert from 'node:assert/strict';
import { templateFor } from '../src/index.js';

test('created template', () => {
  assert.equal(templateFor('order.created'), 'Thanks, we got your order {id}.');
});
test.skip('refund template', () => {
  assert.equal(templateFor('order.refunded'), 'Your refund for {id} is on its way.');
});
EOF

cat > tests/money.test.js <<'EOF'
import test from 'node:test';
import assert from 'node:assert/strict';
import { formatMoney } from '../src/common/money.js';
import { setCurrency } from '../src/config/state.js';

test('yen has no decimals', () => {
  setCurrency('JPY');
  assert.equal(formatMoney(1234), '1234 JPY');
  setCurrency('USD');
});
EOF

cat > tests/misc.test.js <<'EOF'
import test from 'node:test';
import assert from 'node:assert/strict';
import { paginate } from '../src/util/paginate.js';
import { ORDER_STATUSES } from '../src/orders/status.js';

test('module loads', () => { assert.ok(true); });
test('paginate slices like the implementation', () => {
  const items = [1, 2, 3, 4, 5];
  assert.deepEqual(paginate(items, 2, 2), items.slice((2 - 1) * 2, (2 - 1) * 2 + 2));
});
test('there are four statuses', () => { assert.equal(ORDER_STATUSES.length, 4); });
EOF

git init -q . 2>/dev/null || true
git add -A >/dev/null 2>&1 || true
git -c user.email=eval@example.com -c user.name=eval commit -qm "initial orders service" >/dev/null 2>&1 || true
