#!/usr/bin/env bash
set -euo pipefail
git init -q && git config user.email e@example.com && git config user.name eval
mkdir -p src
cat > src/invoices.ts <<'TS'
export interface Db {
  query: (sql: string, values?: unknown[]) => Promise<unknown[]>;
}

export const getInvoice = (db: Db, invoiceId: string) =>
  db.query('SELECT * FROM invoices WHERE id = $1', [invoiceId]);
TS
git add -A && git commit -qm base
cat > src/invoices.ts <<'TS'
export interface Db {
  query: (sql: string, values?: unknown[]) => Promise<unknown[]>;
}

export const getInvoice = (db: Db, invoiceId: string, ownerId: string) =>
  db.query('SELECT * FROM invoices WHERE id = $1 AND owner_id = $2', [invoiceId, ownerId]);
TS
