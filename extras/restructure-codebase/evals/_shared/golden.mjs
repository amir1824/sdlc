// Prints the observable output of the shop library's public API over a fixed grid of inputs.
// Usage: node golden.mjs <shop dir>. Compare the output of a restructured copy with the pristine fixture's.
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const dir = path.resolve(process.argv[2]);
const load = (f) => import(pathToFileURL(path.join(dir, 'src', f)).href);
const [{ cartTotal }, { invoiceLines, invoiceTotal }, { shippingCents }, { refund }, { checkout }] = await Promise.all(
  ['cart.js', 'invoice.js', 'shipping.js', 'refund.js', 'checkout.js'].map(load),
);

const out = {};
const nets = [0, 1, 7, 99, 100, 1003, 1005, 4999, 10000, 12345, 99999, 123457];
const currencies = ['USD', 'JPY', 'EUR'];
const countries = ['IL', 'US', 'DE'];
for (const c of currencies) {
  for (const n of nets) {
    out[`invoiceTotal ${n} ${c}`] = invoiceTotal(n, c);
    out[`invoiceLines ${n} ${c}`] = invoiceLines([{ name: 'a', cents: n }, { name: 'b', cents: -n }], c);
    for (const k of countries) out[`cart ${n} ${c} ${k}`] = cartTotal([{ priceCents: n, qty: 3 }], k, c);
  }
}
for (const k of countries) for (const n of nets) out[`ship ${k} ${n}`] = shippingCents(k, n);
for (const p of ['stripe', 'paypal']) {
  out[`refund ${p}`] = refund({ id: 'o1', provider: p, totalCents: 4200 });
  out[`checkout ${p}`] = await checkout({ id: 'o1', provider: p });
}
console.log(JSON.stringify(out, null, 1));
