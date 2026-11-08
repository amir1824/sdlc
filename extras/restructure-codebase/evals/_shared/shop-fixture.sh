#!/usr/bin/env bash
# Writes the small "shop" library that the restructure-codebase eval cases work on.
# It has duplicated rules, one copy that differs from the others on purpose, a special case
# that must stay, dead code, comments that restate the code, and two tests that prove nothing.
set -euo pipefail
mkdir -p src/payments tests
cat > package.json <<'EOF'
{ "name": "shop", "version": "1.0.0", "type": "module", "scripts": { "test": "node --test" } }
EOF
cat > src/money.js <<'EOF'
export function formatPrice(cents, currency = 'USD') {
  const zeroDecimal = currency === 'JPY';
  const value = zeroDecimal ? cents : cents / 100;
  const text = zeroDecimal ? String(Math.round(value)) : value.toFixed(2);
  return `${text} ${currency}`;
}
EOF
cat > src/cart.js <<'EOF'
import { shippingCents } from './shipping.js';

const TAX = 0.17;

// format a price
function fmt(cents, currency) {
  const v = currency === 'JPY' ? cents : cents / 100;
  return (currency === 'JPY' ? String(Math.round(v)) : v.toFixed(2)) + ' ' + currency;
}

export function cartTotal(items, country, currency = 'USD') {
  let subtotal = 0;
  // loop over the items
  for (const item of items) {
    // add the line price
    subtotal += item.priceCents * item.qty;
  }
  const tax = Math.round(subtotal * TAX);
  const shipping = shippingCents(country, subtotal);
  const totalCents = subtotal + tax + shipping;
  return { subtotal, tax, shipping, totalCents, label: fmt(totalCents, currency) };
}
EOF
cat > src/invoice.js <<'EOF'
const VAT = 0.17;

// format a price, credits in brackets
function fmt(cents, currency) {
  const abs = Math.abs(cents);
  const v = currency === 'JPY' ? abs : abs / 100;
  const text = (currency === 'JPY' ? String(Math.round(v)) : v.toFixed(2)) + ' ' + currency;
  return cents < 0 ? `(${text})` : text;
}

export function invoiceLines(lines, currency = 'USD') {
  // build one text line per entry
  return lines.map((l) => `${l.name}: ${fmt(l.cents, currency)}`);
}

export function invoiceTotal(netCents, currency = 'USD') {
  const gross = Math.floor(netCents * (1 + VAT));
  return `Total: ${fmt(gross, currency)}`;
}
EOF
cat > src/shipping.js <<'EOF'
export function shippingCents(country, subtotal) {
  if (country === 'IL') return subtotal >= 20000 ? 0 : 3000;
  if (country === 'US') return subtotal >= 10000 ? 0 : 1500;
  return 5000;
}
EOF
cat > src/payments/stripe.js <<'EOF'
export function charge(order) { return { id: `st_${order.id}`, provider: 'stripe' }; }
export function refundCharge(id, cents) { return { refunded: cents, via: 'stripe', id }; }
EOF
cat > src/payments/paypal.js <<'EOF'
export function charge(order) { return { id: `pp_${order.id}`, provider: 'paypal' }; }
export function refundPayment(id, cents) { return { refunded: cents, via: 'paypal', id }; }
EOF
cat > src/checkout.js <<'EOF'
import * as stripe from './payments/stripe.js';
import * as paypal from './payments/paypal.js';
import { withRetry } from './retry.js';

export function checkout(order) {
  if (order.provider === 'paypal') return withRetry(async () => paypal.charge(order));
  return withRetry(async () => stripe.charge(order));
}
EOF
cat > src/refund.js <<'EOF'
import * as stripe from './payments/stripe.js';
import * as paypal from './payments/paypal.js';

export function refund(order) {
  if (order.provider === 'paypal') return paypal.refundPayment(order.id, order.totalCents);
  return stripe.refundCharge(order.id, order.totalCents);
}
EOF
cat > src/retry.js <<'EOF'
// the payment gateway drops the first call after each deploy, so we retry once
export async function withRetry(fn) {
  try {
    return await fn();
  } catch {
    return await fn();
  }
}
EOF
cat > src/legacy.js <<'EOF'
export function oldTotal(items) {
  return items.reduce((sum, i) => sum + i.priceCents * i.qty, 0) * 1.17;
}
EOF
cat > tests/cart.test.js <<'EOF'
import test from 'node:test';
import assert from 'node:assert/strict';
import { cartTotal } from '../src/cart.js';

test('totals include tax and shipping', () => {
  const r = cartTotal([{ priceCents: 10000, qty: 2 }], 'IL');
  assert.deepEqual(r, { subtotal: 20000, tax: 3400, shipping: 0, totalCents: 23400, label: '234.00 USD' });
});
test('yen has no decimals', () => {
  assert.equal(cartTotal([{ priceCents: 1000, qty: 1 }], 'US', 'JPY').label, '2670 JPY');
});
test('cart exists', () => { assert.ok(true); });
EOF
cat > tests/invoice.test.js <<'EOF'
import test from 'node:test';
import assert from 'node:assert/strict';
import { invoiceLines, invoiceTotal } from '../src/invoice.js';

test('credits are shown in brackets', () => {
  assert.deepEqual(invoiceLines([{ name: 'Refund', cents: -500 }, { name: 'Item', cents: 1200 }]), ['Refund: (5.00 USD)', 'Item: 12.00 USD']);
});
test('invoice total adds VAT', () => {
  assert.equal(invoiceTotal(10000), 'Total: 117.00 USD');
});
EOF
cat > tests/money.test.js <<'EOF'
import test from 'node:test';
import assert from 'node:assert/strict';
import { formatPrice } from '../src/money.js';

test('formats like the implementation does', () => {
  assert.equal(formatPrice(1234, 'USD'), (1234 / 100).toFixed(2) + ' USD');
});
test('negative amounts keep the minus sign', () => {
  assert.equal(formatPrice(-500, 'USD'), '-5.00 USD');
});
EOF
cat > tests/refund.test.js <<'EOF'
import test from 'node:test';
import assert from 'node:assert/strict';
import { refund } from '../src/refund.js';

test('refunds go to the provider that charged', () => {
  assert.equal(refund({ id: 'a', provider: 'paypal', totalCents: 100 }).via, 'paypal');
  assert.equal(refund({ id: 'b', provider: 'stripe', totalCents: 100 }).via, 'stripe');
});
EOF
git init -q . 2>/dev/null || true
git add -A >/dev/null 2>&1 || true
git -c user.email=eval@example.com -c user.name=eval commit -qm "initial shop library" >/dev/null 2>&1 || true
