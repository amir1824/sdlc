#!/usr/bin/env bash
set -euo pipefail
git init -q && git config user.email e@example.com && git config user.name eval
mkdir -p src
cat > src/orders.ts <<'TS'
export interface Order {
  id: string;
  status: 'new' | 'paid' | 'shipped';
  totalCents: number;
}

export const isPaid = (order: Order): boolean => order.status === 'paid';
TS
git add -A && git commit -qm base
cat > src/orders.ts <<'TS'
import { readFileSync } from 'fs';

export interface Order {
  id: string;
  status: 'new' | 'paid' | 'shipped' | 'refunded';
  totalCents: number;
}

export const isPaid = (order: Order): boolean => order.status === 'paid';

export function describe(order: any, kind: string, locale: string, currency: string) {
  console.log('describing', order);
  switch (kind) {
    case 'new':
      return 'New order';
    case 'paid':
      return 'Paid order';
    case 'shipped':
      return 'Shipped order';
    case 'refunded':
      return 'Refunded order';
  }
  // const legacy = order.total * 100;
  if (order.totalCents > 86400) {
    return 'Large order';
  } else {
    return 'Order';
  }
}
TS
