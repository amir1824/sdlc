#!/usr/bin/env bash
set -euo pipefail
git init -q && git config user.email e@example.com && git config user.name eval
mkdir -p src
cat > src/invoices.ts <<'TS'
export interface Request {
  userId: string;
  params: Record<string, string>;
  headers: Record<string, string>;
}

export interface Db {
  query: (sql: string, values?: unknown[]) => Promise<unknown[]>;
}
TS
git add -A && git commit -qm base
cat > src/invoices.ts <<'TS'
import { readFile } from 'fs/promises';
import { join } from 'path';

export interface Request {
  userId: string;
  params: Record<string, string>;
  headers: Record<string, string>;
}

export interface Db {
  query: (sql: string, values?: unknown[]) => Promise<unknown[]>;
}

const INVOICE_DIR = '/srv/invoices';

export const getInvoice = (db: Db, req: Request) =>
  db.query(`SELECT * FROM invoices WHERE id = '${req.params.id}'`);

export const downloadInvoice = (req: Request) =>
  readFile(join(INVOICE_DIR, req.params.file));

export const logRequest = (req: Request) =>
  process.stdout.write(`request from ${req.userId} auth=${req.headers.authorization}\n`);
TS
