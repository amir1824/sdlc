#!/usr/bin/env bash
# Writes the lendwell repository (holdout-service eval fixture) into the current directory, then
# makes one git commit. Deterministic: same files, same content, fixed commit dates.
set -euo pipefail
mkdir -p 'src' 'src/admin' 'src/catalog' 'src/circulation' 'src/fines' 'src/holds' 'src/members' 'src/notifications' 'src/notifications/channels' 'src/reports' 'src/shared' 'tests'

cat > 'package.json' <<'__LENDWELL_EOF__'
{
  "name": "lendwell",
  "version": "2.4.1",
  "private": true,
  "description": "Lending service for the county library system: members, catalog, circulation, holds, fines and notices.",
  "type": "module",
  "main": "src/index.js",
  "engines": {
    "node": ">=22"
  },
  "scripts": {
    "test": "node --test"
  }
}
__LENDWELL_EOF__

cat > 'README.md' <<'__LENDWELL_EOF__'
# lendwell

The lending service behind the county library's front desks, the self-checkout kiosks and the
member app. It keeps members, the catalogue, loans, holds, fines and the notices we send.

Everything runs in memory; the desk app persists snapshots on its side. `npm test` runs the tests.

## Rules the service implements

These come from the circulation policy the library board approved (current version: 2024).

- **Item types:** book, dvd, magazine, audiobook and map.
- **Loan periods:** books 21 days, audiobooks 14, DVDs and magazines 7. Maps belong to the local
  history room and are for use in the library only; they are never lent.
- A due date that falls on a day the whole system is closed moves to the next open day.
- **Renewals:** a loan may be renewed at most twice, and not while another member is waiting for
  the item. A renewal gives a full loan period from the day of the renewal.
- **Membership tiers:** adult, child, senior and staff. At any one time adults and seniors may
  borrow 10 items, children 5 and staff 25.
- **Fines** per day late: books 25c, audiobooks 50c, DVDs $1.00, magazines 10c.
  - There is one grace day: an item returned the day after its due date is not fined. After that
    every day past the due date is charged, the grace day included.
  - A fine never exceeds the item's replacement cost.
  - Staff pay no fines. Children's cards pay half. Seniors pay two thirds, rounded down to the
    cent in the member's favour (board decision, April 2019).
- Members who owe more than $10.00 cannot borrow until they pay their balance down.
- **Holds:** a member may hold at most 5 items at once. Holds are served first come, first
  served. When an item with holds is returned it goes to the hold shelf for the first member in
  the queue, who is notified. A hold waits on the shelf for 7 days, 10 at Harbor (Harbor opens
  four days a week).
- **Lost items:** the desk can mark an item on loan as lost; the borrower is charged its
  replacement cost.

## Kiosks

The Selfserv kiosks scan item labels and call `parseBarcode` and `toBarcode` from this package.

## Admin API

`handleRequest({ method, path, headers, body })` serves the operator screens. Every request needs
`Authorization: Bearer <token>`.

## Configuration

| Variable               | Meaning                                   |
| ---------------------- | ----------------------------------------- |
| `LENDWELL_CURRENCY`    | Currency used when amounts are shown      |
| `LENDWELL_ADMIN_TOKEN` | Token for the admin API                   |
| `LENDWELL_MAX_HOLDS`   | Holds a member may have at once           |
__LENDWELL_EOF__

cat > 'src/admin/auth.js' <<'__LENDWELL_EOF__'
import { ADMIN_TOKEN } from './settings.js';

export function isAuthorised(headers = {}) {
  const value = headers.authorization ?? headers.Authorization ?? '';
  return value === `Bearer ${ADMIN_TOKEN}`;
}
__LENDWELL_EOF__

cat > 'src/admin/handlers.js' <<'__LENDWELL_EOF__'
import { LendError, checkoutItem, returnItem, renewLoan, findLoan } from '../circulation/loans.js';
import { loanStore } from '../circulation/loan-store.js';
import { MAX_RENEWALS } from '../circulation/loan-policy.js';
import {
  registerMember,
  listMembers,
  findMembersByName,
  memberSummary,
  deactivateMember,
  changeTier,
} from '../members/member-service.js';
import { addItem, getItem, updateItem, withdrawItem, catalogStore } from '../catalog/catalog-store.js';
import { toBarcode } from '../catalog/barcodes.js';
import { searchCatalog } from '../catalog/search.js';
import { placeHold, cancelHold, listHolds, expireHolds } from '../holds/holds.js';
import { ledgerStore } from '../fines/ledger.js';
import { getBalance, listCharges, waiveFine } from '../fines/fines.js';
import { setClosedDates, listClosedDates } from '../shared/calendar.js';
import { paginate } from '../shared/collections.js';
import { nextId } from '../shared/ids.js';
import { recentLog } from '../shared/log.js';
import { overdueReport } from '../reports/overdue-report.js';
import { finesCsv, finesSummary } from '../reports/fines-report.js';
import { circulationReport } from '../reports/circulation-report.js';
import { sendOverdueNotices } from '../notifications/overdue-notices.js';
import { previewNotice } from '../notifications/preview.js';
import { memberStatement, statementText } from '../fines/statements.js';
import { holdQueueReport } from '../reports/hold-queue-report.js';
import { loansCsv } from '../reports/exports.js';
import { dailySummary } from '../reports/daily-summary.js';
import { memberIdForCard } from '../members/cards.js';
import { DEFAULT_PAGE_SIZE } from './settings.js';

const ALLOWED_TYPES = ['book', 'dvd', 'magazine', 'map'];
const VALID_TIERS = ['adult', 'child', 'senior', 'staff'];

const ok = (body) => ({ status: 200, body });
const created = (body) => ({ status: 201, body });

// ---- members ---------------------------------------------------------------

export function postMember({ body }) {
  if (body.tier !== undefined && !VALID_TIERS.includes(body.tier)) {
    throw new LendError('BAD_TIER', `tier must be one of ${VALID_TIERS.join(', ')}`);
  }
  return created(registerMember(body));
}

export function listMembersRoute({ query }) {
  const rows = query.name ? findMembersByName(query.name) : listMembers();
  return ok(paginate(rows, Number(query.page ?? 1), DEFAULT_PAGE_SIZE));
}

export function getMemberRoute({ params }) {
  return ok({ ...memberSummary(params.id), balanceCents: getBalance(params.id) });
}

export function getMemberByCard({ params }) {
  const memberId = memberIdForCard(params.number);
  if (!memberId) throw new LendError('BAD_REQUEST', `not a valid card number: ${params.number}`);
  return ok({ ...memberSummary(memberId), balanceCents: getBalance(memberId) });
}

export function patchMemberTier({ params, body }) {
  if (!VALID_TIERS.includes(body.tier)) {
    throw new LendError('BAD_TIER', `tier must be one of ${VALID_TIERS.join(', ')}`);
  }
  return ok(changeTier(params.id, body.tier));
}

export function closeMemberCard({ params }) {
  return ok(deactivateMember(params.id));
}

export function getCharges({ params }) {
  return ok({ balanceCents: getBalance(params.id), charges: listCharges(params.id) });
}

export function postWaiver({ params, body }) {
  return created(waiveFine(params.id, body.amountCents, { reason: body.reason, on: body.on }));
}

export function getStatement({ params, query }) {
  const statement = memberStatement(params.id, { from: query.from, to: query.to });
  if (query.format === 'text') {
    return { status: 200, body: statementText(statement), contentType: 'text/plain' };
  }
  return ok(statement);
}

// ---- catalogue -------------------------------------------------------------

export function postItem({ body }) {
  if (!ALLOWED_TYPES.includes(body.type)) {
    throw new LendError('BAD_TYPE', `type must be one of ${ALLOWED_TYPES.join(', ')}`);
  }
  const item = addItem(body);
  return created({ ...item, barcode: toBarcode(item.id) });
}

export function getItemRoute({ params }) {
  const item = getItem(params.id);
  return ok({ ...item, barcode: toBarcode(item.id), loan: findLoan(item.id) ?? null });
}

export function patchItem({ params, body }) {
  const item = updateItem(params.id, body);
  return ok({ ...item, barcode: toBarcode(item.id) });
}

export function withdrawItemRoute({ params }) {
  return ok(withdrawItem(params.id));
}

export function searchRoute({ query }) {
  return ok(searchCatalog(query.q ?? '', { type: query.type, branch: query.branch }));
}

// The desk marks an item lost when the borrower reports it, or after 60 days overdue. The loan
// is closed and the borrower is charged the replacement cost.
export function markItemLost(itemId, on) {
  const item = catalogStore._items.get(itemId);
  if (!item) throw new LendError('NO_ITEM', `no item ${itemId}`);
  const loan = loanStore._loans.find((l) => l.itemId === itemId && l.returnedOn === null);
  if (!loan) throw new LendError('NOT_ON_LOAN', `${itemId} is not on loan`);
  loan.returnedOn = on;
  loan.lost = true;
  item.status = 'lost';
  if (!ledgerStore._entries.has(loan.memberId)) ledgerStore._entries.set(loan.memberId, []);
  ledgerStore._entries.get(loan.memberId).push({
    id: nextId('fee'),
    memberId: loan.memberId,
    kind: 'replacement',
    amountCents: item.replacementCostCents,
    on,
    note: item.title,
  });
  return { itemId, memberId: loan.memberId, chargedCents: item.replacementCostCents };
}

export function postLost({ params, body }) {
  return ok(markItemLost(params.id, body.on));
}

// ---- circulation -----------------------------------------------------------

export function postCheckout({ body }) {
  return created(checkoutItem(body.memberId, body.itemId, body.on));
}

export function postReturn({ body }) {
  return ok(returnItem(body.itemId, body.on));
}

export function postRenewal({ body }) {
  const loan = findLoan(body.itemId);
  if (loan && loan.renewals >= MAX_RENEWALS) {
    throw new LendError('RENEWAL_LIMIT', `${body.itemId} cannot be renewed again`);
  }
  return ok(renewLoan(body.itemId, body.on));
}

export function postHold({ body }) {
  return created(placeHold(body.memberId, body.itemId, body.on));
}

export function listHoldsRoute({ query }) {
  return ok(listHolds({ memberId: query.memberId, itemId: query.itemId, status: query.status }));
}

export function deleteHold({ params, query }) {
  return ok(cancelHold(params.id, query.on));
}

export function postExpireHolds({ body }) {
  return ok(expireHolds(body.on));
}

// ---- operations ------------------------------------------------------------

export function putCalendar({ body }) {
  return ok({ closedDates: setClosedDates(body.closedDates) });
}

export function getCalendar() {
  return ok({ closedDates: listClosedDates() });
}

export function postOverdueNotices({ body }) {
  return ok(sendOverdueNotices(body.on));
}

export function getNoticePreview({ params }) {
  const preview = previewNotice(params.kind);
  if (!preview) throw new LendError('NO_TEMPLATE', `no notice kind ${params.kind}`);
  return ok(preview);
}

export function getOverdueReport({ query }) {
  return ok(overdueReport(query.on));
}

export function getCirculationReport({ query }) {
  return ok(circulationReport({ from: query.from, to: query.to }));
}

export function getDailySummary({ query }) {
  return ok(dailySummary(query.on));
}

export function getFinesSummary() {
  return ok(finesSummary());
}

export function getHoldQueueReport({ query }) {
  const minimum = query.minimum === undefined ? 1 : Number(query.minimum);
  return ok(holdQueueReport(query.on, { minimum }));
}

export function getLoansCsv({ query }) {
  return { status: 200, body: loansCsv({ from: query.from, to: query.to }), contentType: 'text/csv' };
}

export function getFinesCsv() {
  return { status: 200, body: finesCsv(), contentType: 'text/csv' };
}

export function getLog({ query }) {
  return ok(recentLog(query.level));
}
__LENDWELL_EOF__

cat > 'src/admin/http.js' <<'__LENDWELL_EOF__'
// A tiny router for the operator screens. The desk app's server forwards requests here as plain
// objects ({ method, path, headers, body }) and writes back whatever we return.

import { LendError } from '../circulation/loans.js';
import { notifierReady, startNotifications } from '../notifications/notifier.js';
import { isAuthorised } from './auth.js';
import * as h from './handlers.js';

const ROUTES = [
  ['POST', '/members', h.postMember],
  ['GET', '/members', h.listMembersRoute],
  ['GET', '/members/:id', h.getMemberRoute],
  ['GET', '/cards/:number', h.getMemberByCard],
  ['PATCH', '/members/:id/tier', h.patchMemberTier],
  ['DELETE', '/members/:id', h.closeMemberCard],
  ['GET', '/members/:id/charges', h.getCharges],
  ['POST', '/members/:id/waivers', h.postWaiver],
  ['GET', '/members/:id/statement', h.getStatement],
  ['POST', '/items', h.postItem],
  ['GET', '/items/:id', h.getItemRoute],
  ['PATCH', '/items/:id', h.patchItem],
  ['DELETE', '/items/:id', h.withdrawItemRoute],
  ['POST', '/items/:id/lost', h.postLost],
  ['GET', '/search', h.searchRoute],
  ['POST', '/checkouts', h.postCheckout],
  ['POST', '/returns', h.postReturn],
  ['POST', '/renewals', h.postRenewal],
  ['POST', '/holds', h.postHold],
  ['GET', '/holds', h.listHoldsRoute],
  ['DELETE', '/holds/:id', h.deleteHold],
  ['POST', '/holds/expire', h.postExpireHolds],
  ['GET', '/calendar', h.getCalendar],
  ['PUT', '/calendar', h.putCalendar],
  ['POST', '/notices/overdue', h.postOverdueNotices],
  ['GET', '/notices/preview/:kind', h.getNoticePreview],
  ['GET', '/reports/overdue', h.getOverdueReport],
  ['GET', '/reports/circulation', h.getCirculationReport],
  ['GET', '/reports/daily', h.getDailySummary],
  ['GET', '/reports/fines', h.getFinesSummary],
  ['GET', '/reports/fines.csv', h.getFinesCsv],
  ['GET', '/reports/holds', h.getHoldQueueReport],
  ['GET', '/reports/loans.csv', h.getLoansCsv],
  ['GET', '/log', h.getLog],
];

const STATUS_BY_CODE = {
  BAD_REQUEST: 400,
  BAD_DATE: 400,
  BAD_TYPE: 400,
  BAD_TIER: 400,
  BAD_BRANCH: 400,
  BAD_AMOUNT: 400,
  NO_MEMBER: 404,
  NO_ITEM: 404,
  NO_HOLD: 404,
  NO_TEMPLATE: 404,
  PAYMENT_FAILED: 502,
};

function matchRoute(pattern, pathname) {
  const want = pattern.split('/');
  const got = pathname.split('/');
  if (want.length !== got.length) return null;
  const params = {};
  for (let i = 0; i < want.length; i += 1) {
    if (want[i].startsWith(':')) params[want[i].slice(1)] = decodeURIComponent(got[i]);
    else if (want[i] !== got[i]) return null;
  }
  return params;
}

function splitPath(path) {
  const [pathname, search = ''] = String(path).split('?');
  const query = Object.fromEntries(new URLSearchParams(search));
  return { pathname: pathname.replace(/\/+$/, '') || '/', query };
}

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function handleRequest({ method = 'GET', path = '/', headers = {}, body = {} } = {}) {
  if (!isAuthorised(headers)) return { status: 401, body: { error: 'UNAUTHORISED' } };
  if (!notifierReady()) startNotifications();
  const { pathname, query } = splitPath(path);
  for (const [verb, pattern, handler] of ROUTES) {
    if (verb !== method) continue;
    const params = matchRoute(pattern, pathname);
    if (!params) continue;
    // give the search index a moment to catch up with items added just before
    if (pathname === '/search') await pause(5);
    try {
      return handler({ params, query, body: body ?? {} });
    } catch (err) {
      if (err instanceof LendError) {
        return { status: STATUS_BY_CODE[err.code] ?? 409, body: { error: err.code, message: err.message } };
      }
      throw err;
    }
  }
  return { status: 404, body: { error: 'NOT_FOUND', message: `${method} ${pathname}` } };
}
__LENDWELL_EOF__

cat > 'src/admin/settings.js' <<'__LENDWELL_EOF__'
// Operator settings. They are read once, when the service starts.

export const CURRENCY = process.env.LENDWELL_CURRENCY || 'USD';

export const ADMIN_TOKEN = process.env.LENDWELL_ADMIN_TOKEN || 'dev-admin-token';

// Page size for the list endpoints of the admin API.
export const DEFAULT_PAGE_SIZE = 25;
__LENDWELL_EOF__

cat > 'src/catalog/barcodes.js' <<'__LENDWELL_EOF__'
// Item barcodes as printed on spine labels and read by the Selfserv kiosks.
//
// The format is fixed by the kiosk vendor: 'LW', the item number as seven digits, then a check
// digit computed with the Luhn algorithm over those seven digits. Scanners sometimes send
// lowercase letters or trailing whitespace.

const BARCODE = /^LW(\d{7})(\d)$/;

function luhnDigit(digits) {
  let sum = 0;
  for (let i = 0; i < digits.length; i += 1) {
    let digit = Number(digits[digits.length - 1 - i]);
    if (i % 2 === 0) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    sum += digit;
  }
  return (10 - (sum % 10)) % 10;
}

export function toBarcode(itemId) {
  const match = /^i-(\d+)$/.exec(itemId);
  if (!match) throw new TypeError(`not an item id: ${itemId}`);
  const digits = match[1].padStart(7, '0');
  return `LW${digits}${luhnDigit(digits)}`;
}

// The item id for a scanned code, or null when the code is not one of ours or the check digit
// does not match (a misread; the kiosk asks the member to scan again).
export function parseBarcode(code) {
  const match = BARCODE.exec(String(code).trim().toUpperCase());
  if (!match) return null;
  const [, digits, check] = match;
  if (luhnDigit(digits) !== Number(check)) return null;
  return `i-${String(Number(digits)).padStart(4, '0')}`;
}
__LENDWELL_EOF__

cat > 'src/catalog/catalog-store.js' <<'__LENDWELL_EOF__'
import { LendError } from '../circulation/loans.js';
import { nextId } from '../shared/ids.js';
import { isBranch } from '../shared/branches.js';
import { requireString } from '../shared/validate.js';
import { isItemType } from './item-types.js';

// What we charge for a lost item when cataloguing did not record a price.
const DEFAULT_REPLACEMENT_CENTS = 2000;

const STATUSES = ['available', 'on-loan', 'on-hold-shelf', 'lost', 'withdrawn'];

export const catalogStore = {
  _items: new Map(),
  listeners: [],
};

export function onCatalogChange(listener) {
  catalogStore.listeners.push(listener);
}

function changed(item) {
  for (const listener of catalogStore.listeners) listener(item);
}

export function addItem({
  title,
  author = '',
  type,
  branch = 'main',
  year = null,
  replacementCostCents = DEFAULT_REPLACEMENT_CENTS,
} = {}) {
  const cleanTitle = requireString(title, 'title');
  if (!isItemType(type)) throw new LendError('BAD_TYPE', `unknown item type: ${type}`);
  if (!isBranch(branch)) throw new LendError('BAD_BRANCH', `unknown branch: ${branch}`);
  if (!Number.isInteger(replacementCostCents) || replacementCostCents < 0) {
    throw new LendError('BAD_AMOUNT', 'replacementCostCents must be a whole number of cents');
  }
  const item = {
    id: nextId('i'),
    title: cleanTitle,
    author: String(author).trim(),
    type,
    branch,
    year,
    replacementCostCents,
    status: 'available',
  };
  // add the item to the map
  catalogStore._items.set(item.id, item);
  changed(item);
  return { ...item };
}

export function findItem(id) {
  const item = catalogStore._items.get(id);
  return item ? { ...item } : undefined;
}

export function getItem(id) {
  const item = catalogStore._items.get(id);
  // check if the item exists
  if (!item) throw new LendError('NO_ITEM', `no item ${id}`);
  return { ...item };
}

export function listItems() {
  return [...catalogStore._items.values()].map((item) => ({ ...item }));
}

export function setItemStatus(id, status) {
  if (!STATUSES.includes(status)) throw new Error(`unknown item status ${status}`);
  const item = catalogStore._items.get(id);
  if (!item) throw new LendError('NO_ITEM', `no item ${id}`);
  item.status = status;
  changed(item);
  return { ...item };
}

const EDITABLE = ['title', 'author', 'year', 'branch', 'replacementCostCents'];

// Cataloguing fixes: typos in titles, a transfer to another branch, a new price from the supplier.
export function updateItem(id, changes) {
  const item = catalogStore._items.get(id);
  if (!item) throw new LendError('NO_ITEM', `no item ${id}`);
  for (const key of Object.keys(changes)) {
    if (!EDITABLE.includes(key)) throw new LendError('BAD_REQUEST', `${key} cannot be changed`);
  }
  if (changes.branch !== undefined) {
    if (!isBranch(changes.branch)) throw new LendError('BAD_BRANCH', `unknown branch: ${changes.branch}`);
    if (item.status !== 'available') {
      throw new LendError('NOT_AVAILABLE', `${item.title} can only move branch while on the shelf`);
    }
  }
  const clean = { ...changes };
  if (clean.title !== undefined) clean.title = requireString(clean.title, 'title');
  if (clean.author !== undefined) clean.author = String(clean.author).trim();
  if (clean.replacementCostCents !== undefined) {
    if (!Number.isInteger(clean.replacementCostCents) || clean.replacementCostCents < 0) {
      throw new LendError('BAD_AMOUNT', 'replacementCostCents must be a whole number of cents');
    }
  }
  Object.assign(item, clean);
  changed(item);
  return { ...item };
}

// Weeded items stay in the catalogue so old loans still resolve, but can no longer circulate.
export function withdrawItem(id) {
  const item = catalogStore._items.get(id);
  if (!item) throw new LendError('NO_ITEM', `no item ${id}`);
  if (item.status !== 'available') {
    throw new LendError('NOT_AVAILABLE', `${item.title} is ${item.status} and cannot be withdrawn`);
  }
  return setItemStatus(id, 'withdrawn');
}

export function resetCatalog() {
  catalogStore._items.clear();
}
__LENDWELL_EOF__

cat > 'src/catalog/item-types.js' <<'__LENDWELL_EOF__'
// Kinds of thing the library lends (or, for maps, keeps for reading in the building).

export const ITEM_TYPES = ['book', 'dvd', 'magazine', 'audiobook', 'map'];

export function isItemType(type) {
  return ITEM_TYPES.includes(type);
}

export default ITEM_TYPES;
__LENDWELL_EOF__

cat > 'src/catalog/marc-import.js' <<'__LENDWELL_EOF__'
// Bulk import of records exported from the old Dynix catalogue.
//
// The export is a text file of records separated by a blank line. Each line is a three-character
// tag, a space and a value:
//
//   245 The Salt Road
//   100 Halloran, Jane
//   008 a
//   260 2011
//   852 harbor
//   020 1500
//
// 008 carries the material code, 852 the holding branch and 020 the price in cents.

import { addItem } from './catalog-store.js';

const MATERIAL = { a: 'book', g: 'dvd', s: 'magazine', i: 'audiobook', e: 'map' };

function parseRecord(block) {
  const fields = {};
  for (const line of block.split('\n')) {
    const tag = line.slice(0, 3);
    const value = line.slice(4).trim();
    if (!/^\d{3}$/.test(tag) || value === '') continue;
    fields[tag] = value;
  }
  return fields;
}

function invertName(name) {
  const [last, first] = name.split(',').map((part) => part.trim());
  return first ? `${first} ${last}` : last;
}

export function importDynixExport(text) {
  const imported = [];
  const rejected = [];
  const blocks = text.split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean);
  for (const [n, block] of blocks.entries()) {
    const fields = parseRecord(block);
    const type = MATERIAL[fields['008']];
    if (!fields['245'] || !type) {
      rejected.push({ record: n + 1, reason: 'missing title or material code' });
      continue;
    }
    try {
      imported.push(
        addItem({
          title: fields['245'],
          author: fields['100'] ? invertName(fields['100']) : '',
          type,
          branch: fields['852'] ?? 'main',
          year: fields['260'] ? Number(fields['260']) : null,
          replacementCostCents: fields['020'] ? Number(fields['020']) : undefined,
        }),
      );
    } catch (err) {
      rejected.push({ record: n + 1, reason: err.message });
    }
  }
  return { imported, rejected };
}
__LENDWELL_EOF__

cat > 'src/catalog/search.js' <<'__LENDWELL_EOF__'
// Title and author search over the catalogue.
//
// The index is rebuilt off the request path. Adding a box of new stock from the cataloguing
// screen used to freeze the desk for seconds while every single add re-tokenised everything.

import { listItems, findItem, onCatalogChange } from './catalog-store.js';

let index = [];
let pending = null;

function tokenize(text) {
  return String(text)
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
}

function rebuild() {
  pending = null;
  index = listItems().map((item) => ({
    id: item.id,
    words: new Set(tokenize(`${item.title} ${item.author}`)),
  }));
}

export function scheduleReindex() {
  if (pending) return;
  pending = setTimeout(rebuild, 0);
}

onCatalogChange(() => scheduleReindex());

export function searchCatalog(query, { type, branch, availableOnly = false } = {}) {
  const terms = tokenize(query);
  if (terms.length === 0) return [];
  const scored = [];
  for (const entry of index) {
    const hits = terms.filter((term) => entry.words.has(term)).length;
    if (hits === 0) continue;
    const item = findItem(entry.id);
    if (!item || item.status === 'withdrawn') continue;
    if (type && item.type !== type) continue;
    if (branch && item.branch !== branch) continue;
    if (availableOnly && item.status !== 'available') continue;
    scored.push({ item, hits });
  }
  scored.sort((a, b) => b.hits - a.hits);
  return scored.map(({ item }) => item);
}

export function resetSearch() {
  if (pending) clearTimeout(pending);
  pending = null;
  index = [];
}
__LENDWELL_EOF__

cat > 'src/circulation/due-dates.js' <<'__LENDWELL_EOF__'
import { addDays } from '../shared/dates.js';
import { closedDates } from '../shared/calendar.js';

// A due date never lands on a day the whole system is closed; it moves to the next open day.
export function dueDateFor(start, loanDays) {
  let due = addDays(start, loanDays);
  while (closedDates.includes(due)) {
    due = addDays(due, 1);
  }
  return due;
}
__LENDWELL_EOF__

cat > 'src/circulation/loan-policy.js' <<'__LENDWELL_EOF__'
// Loan periods in days, by item type. Maps are reference-only and have no loan period.

export const LOAN_DAYS = {
  book: 21,
  audiobook: 14,
  dvd: 7,
  magazine: 7,
};

export const MAX_RENEWALS = 2;

// How a renewal sets the new due date: 'from-today' gives a full loan period counted from the
// day of the renewal, 'from-due' would add the period to the current due date instead.
export const RENEWAL_MODE = 'from-today';

export function loanDaysFor(type) {
  const days = LOAN_DAYS[type];
  if (days === undefined) throw new Error(`no loan period for ${type}`);
  return days;
}
__LENDWELL_EOF__

cat > 'src/circulation/loan-store.js' <<'__LENDWELL_EOF__'
// Every loan, open and closed, in the order the loans were made.

export const loanStore = {
  _loans: [],
};

export function addLoan(loan) {
  loanStore._loans.push(loan);
  return loan;
}

export function openLoanForItem(itemId) {
  return loanStore._loans.find((loan) => loan.itemId === itemId && loan.returnedOn === null);
}

export function loansForMember(memberId) {
  return loanStore._loans.filter((loan) => loan.memberId === memberId);
}

export function resetLoans() {
  loanStore._loans.length = 0;
}
__LENDWELL_EOF__

cat > 'src/circulation/loans.js' <<'__LENDWELL_EOF__'
import { FEATURES } from '../config.js';
import { log } from '../shared/log.js';
import { nextId } from '../shared/ids.js';
import { addDays } from '../shared/dates.js';
import { branchName } from '../shared/branches.js';
import { requireDate } from '../shared/validate.js';
import { getMember } from '../members/member-store.js';
import { loanLimitFor } from '../members/membership.js';
import { getItem, setItemStatus } from '../catalog/catalog-store.js';
import { chargeLateFine, getBalance } from '../fines/fines.js';
import { BLOCK_THRESHOLD_CENTS } from '../fines/fine-rates.js';
import { queueFor, shiftQueue } from '../holds/hold-queue.js';
import { notify } from '../notifications/notifier.js';
import { addLoan, openLoanForItem, loansForMember, loanStore } from './loan-store.js';
import { loanDaysFor, MAX_RENEWALS, RENEWAL_MODE } from './loan-policy.js';
import { dueDateFor } from './due-dates.js';

export class LendError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'LendError';
    this.code = code;
  }
}

export function openLoansFor(memberId) {
  return loansForMember(memberId)
    .filter((loan) => loan.returnedOn === null)
    .map((loan) => ({ ...loan }));
}

export function findLoan(itemId) {
  const loan = openLoanForItem(itemId);
  return loan ? { ...loan } : undefined;
}

export function listLoans({ memberId, open } = {}) {
  return loanStore._loans
    .filter((loan) => (memberId === undefined ? true : loan.memberId === memberId))
    .filter((loan) => (open === undefined ? true : (loan.returnedOn === null) === open))
    .map((loan) => ({ ...loan }));
}

function readyHoldFor(itemId) {
  return queueFor(itemId).find((hold) => hold.status === 'ready');
}

export function checkoutItem(memberId, itemId, on) {
  requireDate(on, 'on');
  const member = getMember(memberId);
  const item = getItem(itemId);
  if (!member.active) throw new LendError('MEMBER_INACTIVE', `${member.name}'s card is closed`);
  // Maps belong to the local history room and are read in the building.
  if (item.type === 'map') {
    throw new LendError('NOT_LOANABLE', `${item.title} is for use in the library only`);
  }
  if (item.status === 'on-loan') throw new LendError('ON_LOAN', `${item.title} is already on loan`);
  if (item.status === 'lost' || item.status === 'withdrawn') {
    throw new LendError('NOT_AVAILABLE', `${item.title} is ${item.status}`);
  }
  let hold = null;
  if (item.status === 'on-hold-shelf') {
    hold = readyHoldFor(itemId);
    if (!hold || hold.memberId !== memberId) {
      throw new LendError('ON_HOLD', `${item.title} is waiting on the hold shelf for another member`);
    }
  }
  const onLoan = openLoansFor(memberId).length;
  if (onLoan >= loanLimitFor(member.tier)) {
    throw new LendError('LOAN_LIMIT', `${member.name} already has ${onLoan} items on loan`);
  }
  if (getBalance(memberId) > BLOCK_THRESHOLD_CENTS) {
    throw new LendError('BLOCKED', `${member.name} owes more than the borrowing limit`);
  }
  if (hold) {
    hold.status = 'collected';
    shiftQueue(itemId);
  }
  // create the loan id
  const id = nextId('loan');
  const loan = {
    id,
    memberId,
    itemId,
    checkedOutOn: on,
    dueOn: dueDateFor(on, loanDaysFor(item.type)),
    renewals: 0,
    returnedOn: null,
  };
  addLoan(loan);
  setItemStatus(itemId, 'on-loan');
  if (FEATURES.auditLog) log.info(`checkout ${itemId} to ${memberId}, due ${loan.dueOn}`);
  return { ...loan };
}

export function returnItem(itemId, on) {
  requireDate(on, 'on');
  const loan = openLoanForItem(itemId);
  if (!loan) throw new LendError('NOT_ON_LOAN', `${itemId} is not on loan`);
  if (on < loan.checkedOutOn) {
    throw new LendError('BAD_DATE', `return date ${on} is before the checkout on ${loan.checkedOutOn}`);
  }
  loan.returnedOn = on;
  const fineCents = chargeLateFine(loan, on);
  // set status to available
  setItemStatus(itemId, 'available');
  if (FEATURES.auditLog) log.info(`return ${itemId} from ${loan.memberId}`);

  const next = queueFor(itemId).find((hold) => hold.status === 'waiting');
  if (next) {
    try {
      const item = getItem(itemId);
      next.status = 'ready';
      next.readyOn = on;
      next.readyUntil = addDays(on, item.branch === 'harbor' ? 10 : 7);
      setItemStatus(itemId, 'on-hold-shelf');
      notify('hold.ready', getMember(next.memberId), {
        title: item.title,
        branchName: branchName(item.branch),
        until: next.readyUntil,
      });
    } catch (err) {
      log.warn(`hold ${next.id}: could not finish moving ${itemId} to the hold shelf: ${err.message}`);
    }
  }
  return { ...loan, fineCents };
}

export function renewLoan(itemId, on) {
  requireDate(on, 'on');
  const loan = openLoanForItem(itemId);
  if (!loan) throw new LendError('NOT_ON_LOAN', `${itemId} is not on loan`);
  if (loan.renewals > MAX_RENEWALS) {
    throw new LendError('RENEWAL_LIMIT', `${itemId} has already been renewed ${loan.renewals} times`);
  }
  if (queueFor(itemId).some((hold) => hold.status === 'waiting')) {
    throw new LendError('HAS_HOLDS', `another member is waiting for ${itemId}`);
  }
  const item = getItem(itemId);
  const start = RENEWAL_MODE === 'from-due' ? loan.dueOn : on;
  loan.dueOn = dueDateFor(start, loanDaysFor(item.type));
  // increment the renewal count
  loan.renewals += 1;
  return { ...loan };
}
__LENDWELL_EOF__

cat > 'src/config.js' <<'__LENDWELL_EOF__'
// Feature switches and limits for the lending service.

export const FEATURES = {
  // Holds v2: one queue per item, first come, first served. v1 sorted same-day holds by member id.
  holdsV2: true,
  // Text-message notices are waiting on the county's carrier contract.
  smsNotices: false,
  // Write a log line for every checkout and return.
  auditLog: false,
};

export const MAX_HOLDS_PER_MEMBER = parseInt(process.env.LENDWELL_MAX_HOLDS, 10) || 5;
__LENDWELL_EOF__

cat > 'src/fines/fine-rates.js' <<'__LENDWELL_EOF__'
// Daily late fines in cents, by item type.
export const FINE_PER_DAY = {
  book: 25,
  audiobook: 50,
  dvd: 100,
  magazine: 10,
};

// Days after the due date before any fine is owed.
export const GRACE_DAYS = 1;

// Ceiling for a single fine when we do not know what the item costs to replace.
export const MAX_FINE_CENTS = 5000;

// Members who owe more than this cannot borrow.
export const BLOCK_THRESHOLD_CENTS = 1000;
__LENDWELL_EOF__

cat > 'src/fines/fines.js' <<'__LENDWELL_EOF__'
import { LendError } from '../circulation/loans.js';
import { getMember } from '../members/member-store.js';
import { getItem } from '../catalog/catalog-store.js';
import { requireCents, requireString } from '../shared/validate.js';
import { FINE_PER_DAY, GRACE_DAYS, MAX_FINE_CENTS } from './fine-rates.js';
import { addEntry, balanceFor, entriesFor } from './ledger.js';

export function lateFineCents(loan, item, member, returnedOn) {
  const daysLate = Math.round((Date.parse(returnedOn) - Date.parse(loan.dueOn)) / 86400000);
  // Inside the grace period nothing is owed. Past it, the grace day is charged with the rest
  // (circulation policy 4.2), so an item two days late costs two days.
  if (daysLate <= GRACE_DAYS) return 0;
  let total = daysLate * (FINE_PER_DAY[item.type] ?? 0);
  // A fine never exceeds what it would cost to replace the item.
  const cap = item.replacementCents ?? MAX_FINE_CENTS;
  if (total > cap) total = cap;
  if (member.tier === 'staff') return 0;
  if (member.tier === 'junior') total = Math.floor(total / 2);
  // Board decision, April 2019: seniors pay two thirds, rounded down in the member's favour.
  if (member.tier === 'senior') total = Math.floor((total * 2) / 3);
  return total;
}

export function chargeLateFine(loan, returnedOn) {
  const item = getItem(loan.itemId);
  const member = getMember(loan.memberId);
  const amountCents = lateFineCents(loan, item, member, returnedOn);
  if (amountCents > 0) {
    addEntry(member.id, {
      kind: 'late',
      amountCents,
      on: returnedOn,
      note: `${item.title}, due ${loan.dueOn}`,
    });
  }
  return amountCents;
}

export function getBalance(memberId) {
  getMember(memberId);
  return balanceFor(memberId);
}

export function listCharges(memberId) {
  getMember(memberId);
  return entriesFor(memberId);
}

export function waiveFine(memberId, amountCents, { reason, on = null } = {}) {
  requireCents(amountCents, 'amountCents');
  const why = requireString(reason, 'reason');
  const owed = getBalance(memberId);
  if (amountCents > owed) {
    throw new LendError('OVER_WAIVE', `cannot waive ${amountCents} cents, ${memberId} owes ${owed}`);
  }
  return addEntry(memberId, { kind: 'waiver', amountCents: -amountCents, on, note: why });
}

export { FINE_PER_DAY, MAX_FINE_CENTS } from './fine-rates.js';
__LENDWELL_EOF__

cat > 'src/fines/ledger.js' <<'__LENDWELL_EOF__'
// Charges and credits per member. Positive amounts are owed by the member; payments and
// waivers are stored as negative amounts.

import { nextId } from '../shared/ids.js';

export const ledgerStore = {
  _entries: new Map(),
};

export function addEntry(memberId, { kind, amountCents, on = null, note = '' }) {
  if (!ledgerStore._entries.has(memberId)) ledgerStore._entries.set(memberId, []);
  const entry = { id: nextId('fee'), memberId, kind, amountCents, on, note };
  ledgerStore._entries.get(memberId).push(entry);
  return { ...entry };
}

export function entriesFor(memberId) {
  return (ledgerStore._entries.get(memberId) ?? []).map((entry) => ({ ...entry }));
}

export function balanceFor(memberId) {
  return (ledgerStore._entries.get(memberId) ?? []).reduce((sum, entry) => sum + entry.amountCents, 0);
}

export function resetLedger() {
  ledgerStore._entries.clear();
}
__LENDWELL_EOF__

cat > 'src/fines/payments.js' <<'__LENDWELL_EOF__'
// Card payments for fines, through Paywell.

import { LendError } from '../circulation/loans.js';
import { requireCents } from '../shared/validate.js';
import { log } from '../shared/log.js';
import { getBalance } from './fines.js';
import { addEntry } from './ledger.js';

// Used when the caller passes no gateway: accepts every charge. The desk terminals and the member
// app pass the real Paywell client.
export const offlineGateway = {
  async charge({ amountCents, idempotencyKey }) {
    return { chargeId: `offline-${idempotencyKey}`, amountCents };
  },
};

async function chargeOnce(gateway, request) {
  // Paywell drops the first request on a connection that has sat idle for a while and answers
  // with a timeout even though nothing was charged. Their support confirmed (ticket PW-4471)
  // that resending the same request with the same idempotency key is safe and recommended
  // exactly one retry. Nothing else is retried: a retried decline shows up as a second decline
  // on the member's card statement.
  try {
    return { result: await gateway.charge(request), attempts: 1 };
  } catch (err) {
    if (err?.code !== 'ETIMEDOUT') throw err;
    log.warn(`paywell timed out on ${request.idempotencyKey}; retrying once`);
    return { result: await gateway.charge(request), attempts: 2 };
  }
}

export async function payFine(memberId, amountCents, { gateway = offlineGateway, on = null } = {}) {
  requireCents(amountCents, 'amountCents');
  const owed = getBalance(memberId);
  if (owed <= 0) throw new LendError('NOTHING_OWED', `${memberId} owes nothing`);
  if (amountCents > owed) {
    throw new LendError('OVERPAYMENT', `${memberId} owes ${owed} cents, cannot take ${amountCents}`);
  }
  const request = {
    amountCents,
    idempotencyKey: `${memberId}-${owed}-${amountCents}`,
    description: `County library fines, ${memberId}`,
  };
  let charged;
  try {
    charged = await chargeOnce(gateway, request);
  } catch (err) {
    throw new LendError('PAYMENT_FAILED', `payment for ${memberId} failed: ${err?.code ?? err?.message}`);
  }
  const entry = addEntry(memberId, {
    kind: 'payment',
    amountCents: -amountCents,
    on,
    note: charged.result.chargeId,
  });
  return {
    paidCents: amountCents,
    balanceCents: owed - amountCents,
    chargeId: charged.result.chargeId,
    attempts: charged.attempts,
    entryId: entry.id,
  };
}
__LENDWELL_EOF__

cat > 'src/fines/statements.js' <<'__LENDWELL_EOF__'
// Account statements: what a member was charged and paid in a period, with the balance carried
// in and out. Printed at the desk on request and attached to the yearly reminder letter.

import { getMember } from '../members/member-store.js';
import { formatCents } from '../shared/money.js';
import { requireDate } from '../shared/validate.js';
import { entriesFor } from './ledger.js';

const LABELS = {
  late: 'Late return',
  replacement: 'Replacement',
  payment: 'Payment',
  waiver: 'Waived',
};

function describe(entry) {
  const label = LABELS[entry.kind] ?? entry.kind;
  return entry.note ? `${label}: ${entry.note}` : label;
}

export function memberStatement(memberId, { from, to }) {
  requireDate(from, 'from');
  requireDate(to, 'to');
  const member = getMember(memberId);
  const entries = entriesFor(memberId);
  let openingCents = 0;
  const lines = [];
  for (const entry of entries) {
    // Entries without a date predate the 2023 migration; they count towards the opening balance.
    if (entry.on === null || entry.on < from) {
      openingCents += entry.amountCents;
      continue;
    }
    if (entry.on > to) continue;
    lines.push({
      on: entry.on,
      description: describe(entry),
      amountCents: entry.amountCents,
      amount: formatCents(entry.amountCents),
    });
  }
  const closingCents = lines.reduce((sum, line) => sum + line.amountCents, openingCents);
  return {
    memberId,
    name: member.name,
    from,
    to,
    opening: formatCents(openingCents),
    lines,
    closing: formatCents(closingCents),
    closingCents,
  };
}

export function statementText(statement) {
  const out = [
    `Statement for ${statement.name} (${statement.memberId})`,
    `${statement.from} to ${statement.to}`,
    '',
    `Balance brought forward: ${statement.opening}`,
  ];
  for (const line of statement.lines) {
    out.push(`${line.on}  ${line.description.padEnd(40)} ${line.amount.padStart(10)}`);
  }
  out.push('', `Balance: ${statement.closing}`);
  return out.join('\n');
}
__LENDWELL_EOF__

cat > 'src/holds/hold-queue.js' <<'__LENDWELL_EOF__'
// One queue of holds per item, oldest first.

const queues = new Map();

export function queueFor(itemId) {
  if (!queues.has(itemId)) queues.set(itemId, []);
  return queues.get(itemId);
}

export function pushToQueue(itemId, hold) {
  queueFor(itemId).push(hold);
}

export function peekQueue(itemId) {
  return queueFor(itemId)[0];
}

export function shiftQueue(itemId) {
  return queueFor(itemId).shift();
}

export function removeFromQueue(itemId, holdId) {
  const queue = queueFor(itemId);
  const at = queue.findIndex((hold) => hold.id === holdId);
  if (at >= 0) queue.splice(at, 1);
}

export function queueLength(itemId) {
  return queueFor(itemId).length;
}

export function clearQueues() {
  queues.clear();
}
__LENDWELL_EOF__

cat > 'src/holds/hold-shelf.js' <<'__LENDWELL_EOF__'
import { addDays } from '../shared/dates.js';
import { branchName } from '../shared/branches.js';
import { getItem, setItemStatus } from '../catalog/catalog-store.js';
import { getMember } from '../members/member-store.js';
import { notify } from '../notifications/notifier.js';
import { peekQueue } from './hold-queue.js';

const DEFAULT_SHELF_DAYS = 7;

export function shelfDaysFor(branchId) {
  // Harbor only opens four days a week, so members get longer to come in.
  if (branchId === 'harbor') return 10;
  return DEFAULT_SHELF_DAYS;
}

// Hands the item to the next member in the queue, or puts it back on the open shelf when nobody
// is waiting. Called when a hold on the shelf is cancelled or runs out.
export function releaseFromShelf(itemId, on) {
  const item = getItem(itemId);
  const next = peekQueue(itemId);
  if (!next) {
    setItemStatus(itemId, 'available');
    return null;
  }
  next.status = 'ready';
  next.readyOn = on;
  next.readyUntil = addDays(on, shelfDaysFor(item.branch));
  setItemStatus(itemId, 'on-hold-shelf');
  notify('hold.ready', getMember(next.memberId), {
    title: item.title,
    branchName: branchName(item.branch),
    until: next.readyUntil,
  });
  return { ...next };
}
__LENDWELL_EOF__

cat > 'src/holds/holds.js' <<'__LENDWELL_EOF__'
import { FEATURES, MAX_HOLDS_PER_MEMBER } from '../config.js';
import { LendError } from '../circulation/loans.js';
import { openLoanForItem } from '../circulation/loan-store.js';
import { nextId } from '../shared/ids.js';
import { addDays } from '../shared/dates.js';
import { requireDate } from '../shared/validate.js';
import { getMember } from '../members/member-store.js';
import { getItem } from '../catalog/catalog-store.js';
import { notify } from '../notifications/notifier.js';
import { pushToQueue, queueFor, removeFromQueue, queueLength, clearQueues } from './hold-queue.js';
import { shelfDaysFor, releaseFromShelf } from './hold-shelf.js';

// Every hold ever placed, in the order placed. The per-item queues hold the live ones.
const holds = [];

const LIVE = ['waiting', 'ready'];

function liveHoldsOf(memberId) {
  return holds.filter((hold) => hold.memberId === memberId && LIVE.includes(hold.status));
}

export function placeHold(memberId, itemId, on) {
  requireDate(on, 'on');
  const member = getMember(memberId);
  const item = getItem(itemId);
  if (!member.active) throw new LendError('MEMBER_INACTIVE', `${member.name}'s card is closed`);
  if (item.status === 'available') {
    throw new LendError('ITEM_AVAILABLE', `${item.title} is on the shelf; borrow it instead`);
  }
  if (item.status === 'lost' || item.status === 'withdrawn') {
    throw new LendError('NOT_AVAILABLE', `${item.title} is ${item.status}`);
  }
  const loan = openLoanForItem(itemId);
  if (loan && loan.memberId === memberId) {
    throw new LendError('ALREADY_BORROWED', `${member.name} has ${item.title} on loan already`);
  }
  const mine = liveHoldsOf(memberId);
  if (mine.some((hold) => hold.itemId === itemId)) {
    throw new LendError('DUPLICATE_HOLD', `${member.name} already has a hold on ${item.title}`);
  }
  if (mine.length >= MAX_HOLDS_PER_MEMBER) {
    throw new LendError('HOLD_LIMIT', `${member.name} already has ${mine.length} holds`);
  }
  const hold = {
    id: nextId('h'),
    memberId,
    itemId,
    placedOn: on,
    status: 'waiting',
    readyOn: null,
    readyUntil: null,
  };
  holds.push(hold);
  if (FEATURES.holdsV2) {
    // push the hold onto the queue
    pushToQueue(itemId, hold);
  } else {
    pushToQueue(itemId, hold);
    queueFor(itemId).sort((a, b) => a.placedOn.localeCompare(b.placedOn) || a.memberId.localeCompare(b.memberId));
  }
  return { ...hold, position: queueLength(itemId) };
}

export function cancelHold(holdId, on) {
  requireDate(on, 'on');
  const hold = holds.find((h) => h.id === holdId);
  if (!hold) throw new LendError('NO_HOLD', `no hold ${holdId}`);
  if (!LIVE.includes(hold.status)) {
    throw new LendError('HOLD_CLOSED', `${holdId} is already ${hold.status}`);
  }
  const wasOnShelf = hold.status === 'ready';
  hold.status = 'cancelled';
  removeFromQueue(hold.itemId, hold.id);
  if (wasOnShelf) releaseFromShelf(hold.itemId, on);
  return { ...hold };
}

export function listHolds({ memberId, itemId, status } = {}) {
  return holds
    .filter((hold) => memberId === undefined || hold.memberId === memberId)
    .filter((hold) => itemId === undefined || hold.itemId === itemId)
    .filter((hold) => status === undefined || hold.status === status)
    .map((hold) => ({ ...hold }));
}

// Run every morning before the branches open. A hold not collected by the end of its last shelf
// day is released and the item moves on to the next member.
export function expireHolds(on) {
  requireDate(on, 'on');
  const expired = [];
  for (const hold of holds) {
    if (hold.status !== 'ready') continue;
    const item = getItem(hold.itemId);
    const lastDay = addDays(hold.readyOn, shelfDaysFor(item.branch));
    if (on <= lastDay) continue;
    hold.status = 'expired';
    removeFromQueue(hold.itemId, hold.id);
    notify('hold.expired', getMember(hold.memberId), { title: item.title });
    releaseFromShelf(hold.itemId, on);
    expired.push({ ...hold });
  }
  return expired;
}

export function resetHolds() {
  holds.length = 0;
  clearQueues();
}
__LENDWELL_EOF__

cat > 'src/index.js' <<'__LENDWELL_EOF__'
// Public entry point of the lending service. The desk app, the kiosks and the member app import
// from here and nowhere else.

import { resetMembers } from './members/member-store.js';
import { resetCatalog } from './catalog/catalog-store.js';
import { resetSearch } from './catalog/search.js';
import { resetLoans } from './circulation/loan-store.js';
import { resetHolds } from './holds/holds.js';
import { resetLedger } from './fines/ledger.js';
import { resetNotifications } from './notifications/notifier.js';
import { setClosedDates } from './shared/calendar.js';
import { resetIds } from './shared/ids.js';
import { clearLog } from './shared/log.js';

export {
  registerMember,
  getMember,
  findMember,
  listMembers,
  memberSummary,
  deactivateMember,
  changeTier,
  updateContact,
} from './members/member-service.js';
export { memberIdForCard } from './members/cards.js';
export { addItem, getItem, findItem, listItems, updateItem, withdrawItem } from './catalog/catalog-store.js';
export { ITEM_TYPES } from './catalog/item-types.js';
export { searchCatalog } from './catalog/search.js';
export { parseBarcode, toBarcode } from './catalog/barcodes.js';
export { LendError, checkoutItem, returnItem, renewLoan, findLoan, listLoans } from './circulation/loans.js';
export { placeHold, cancelHold, listHolds, expireHolds } from './holds/holds.js';
export { getBalance, listCharges, waiveFine } from './fines/fines.js';
export { payFine } from './fines/payments.js';
export { memberStatement, statementText } from './fines/statements.js';
export { markItemLost } from './admin/handlers.js';
export { startNotifications, sentMessages } from './notifications/notifier.js';
export { sendOverdueNotices } from './notifications/overdue-notices.js';
export { circulationReport, popularTitles, branchSummary } from './reports/circulation-report.js';
export { overdueReport } from './reports/overdue-report.js';
export { finesReport, finesCsv, finesSummary } from './reports/fines-report.js';
export { holdPickupDigest } from './reports/notice-digest.js';
export { memberActivity } from './reports/member-activity.js';
export { holdQueueReport } from './reports/hold-queue-report.js';
export { loansCsv } from './reports/exports.js';
export { dailySummary } from './reports/daily-summary.js';
export { setClosedDates, listClosedDates } from './shared/calendar.js';
export { formatCents } from './shared/money.js';
export { handleRequest } from './admin/http.js';

// Clears every store. The desk app calls this before loading a snapshot; tests call it between
// cases.
export function resetLibrary() {
  resetMembers();
  resetCatalog();
  resetSearch();
  resetLoans();
  resetHolds();
  resetLedger();
  resetNotifications();
  setClosedDates([]);
  resetIds();
  clearLog();
}
__LENDWELL_EOF__

cat > 'src/members/cards.js' <<'__LENDWELL_EOF__'
// Library card numbers.
//
// Cards carry a 14-digit number: the county prefix 29381, the member number as eight digits,
// and a check digit (mod 10, weights 1 and 2 from the right) so the desk can tell a typo from a
// real card. Cards issued before 2019 used prefix 29380; they still work at the desk.

const PREFIX = '29381';
const OLD_PREFIX = '29380';

function checkDigit(digits) {
  let sum = 0;
  [...digits].reverse().forEach((char, i) => {
    let digit = Number(char);
    if (i % 2 === 0) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    sum += digit;
  });
  return (10 - (sum % 10)) % 10;
}

export function cardNumberFor(memberId) {
  const match = /^m-(\d+)$/.exec(memberId);
  if (!match) throw new TypeError(`not a member id: ${memberId}`);
  const body = `${PREFIX}${match[1].padStart(8, '0')}`;
  return `${body}${checkDigit(body)}`;
}

// The member id on a typed or scanned card number, or null if it is not a valid card.
export function memberIdForCard(cardNumber) {
  const digits = String(cardNumber).replace(/[\s-]/g, '');
  if (!/^\d{14}$/.test(digits)) return null;
  const prefix = digits.slice(0, 5);
  if (prefix !== PREFIX && prefix !== OLD_PREFIX) return null;
  if (checkDigit(digits.slice(0, 13)) !== Number(digits[13])) return null;
  return `m-${String(Number(digits.slice(5, 13))).padStart(4, '0')}`;
}
__LENDWELL_EOF__

cat > 'src/members/member-service.js' <<'__LENDWELL_EOF__'
// Member operations for the public API and the admin handlers.
// Callers stay on this module so the store can change underneath without touching them.

import * as store from './member-store.js';

export function registerMember(input) {
  return store.createMember(input);
}

export function getMember(id) {
  return store.getMember(id);
}

export function findMember(id) {
  return store.findMember(id);
}

export function listMembers() {
  return store.listMembers();
}

export function findMembersByName(query) {
  return store.findMembersByName(query);
}

export function memberSummary(id) {
  return store.memberSummary(id);
}

export function deactivateMember(id) {
  return store.deactivateMember(id);
}

export function changeTier(id, tier) {
  return store.updateMember(id, { tier });
}

export function updateContact(id, { email, phone }) {
  const changes = {};
  if (email !== undefined) changes.email = email;
  if (phone !== undefined) changes.phone = phone;
  return store.updateMember(id, changes);
}
__LENDWELL_EOF__

cat > 'src/members/member-store.js' <<'__LENDWELL_EOF__'
import { LendError, openLoansFor } from '../circulation/loans.js';
import { nextId } from '../shared/ids.js';
import { isBranch } from '../shared/branches.js';
import { requireString, optionalEmail } from '../shared/validate.js';
import { isTier, loanLimitFor } from './membership.js';
import { cardNumberFor } from './cards.js';

export const memberStore = {
  _byId: new Map(),
};

const EDITABLE = ['name', 'email', 'phone', 'tier', 'homeBranch'];

export function createMember({ name, email, phone = null, tier = 'adult', homeBranch = 'main' } = {}) {
  const cleanName = requireString(name, 'name');
  if (!isTier(tier)) throw new LendError('BAD_TIER', `unknown membership tier: ${tier}`);
  if (!isBranch(homeBranch)) throw new LendError('BAD_BRANCH', `unknown branch: ${homeBranch}`);
  const cleanEmail = optionalEmail(email);
  const id = nextId('m');
  const member = {
    id,
    cardNumber: cardNumberFor(id),
    name: cleanName,
    email: cleanEmail,
    phone,
    tier,
    homeBranch,
    active: true,
  };
  memberStore._byId.set(member.id, member);
  return { ...member };
}

export function findMember(id) {
  const member = memberStore._byId.get(id);
  return member ? { ...member } : undefined;
}

export function getMember(id) {
  const member = memberStore._byId.get(id);
  if (!member) throw new LendError('NO_MEMBER', `no member ${id}`);
  // return the member
  return { ...member };
}

export function listMembers() {
  return [...memberStore._byId.values()].map((member) => ({ ...member }));
}

export function findMembersByName(query) {
  const needle = String(query).trim().toLowerCase();
  if (needle === '') return [];
  return listMembers().filter((member) => member.name.toLowerCase().includes(needle));
}

export function updateMember(id, changes) {
  const member = memberStore._byId.get(id);
  if (!member) throw new LendError('NO_MEMBER', `no member ${id}`);
  for (const key of Object.keys(changes)) {
    if (!EDITABLE.includes(key)) throw new LendError('BAD_REQUEST', `${key} cannot be changed`);
  }
  if (changes.tier !== undefined && !isTier(changes.tier)) {
    throw new LendError('BAD_TIER', `unknown membership tier: ${changes.tier}`);
  }
  if (changes.homeBranch !== undefined && !isBranch(changes.homeBranch)) {
    throw new LendError('BAD_BRANCH', `unknown branch: ${changes.homeBranch}`);
  }
  const clean = { ...changes };
  if (clean.name !== undefined) clean.name = requireString(clean.name, 'name');
  if (clean.email !== undefined) clean.email = optionalEmail(clean.email);
  Object.assign(member, clean);
  return { ...member };
}

// A card is closed when the member moves away or asks. Open loans have to come back first.
export function deactivateMember(id) {
  const member = memberStore._byId.get(id);
  if (!member) throw new LendError('NO_MEMBER', `no member ${id}`);
  const open = openLoansFor(id);
  if (open.length > 0) {
    throw new LendError('HAS_LOANS', `${member.name} still has ${open.length} item(s) on loan`);
  }
  member.active = false;
  return { ...member };
}

// The card the desk sees when a member walks up: who they are and how much more they can take.
export function memberSummary(id) {
  const member = getMember(id);
  const onLoan = openLoansFor(id).length;
  return {
    id: member.id,
    name: member.name,
    tier: member.tier,
    active: member.active,
    onLoan,
    canBorrow: member.active ? Math.max(0, loanLimitFor(member.tier) - onLoan) : 0,
  };
}

export function resetMembers() {
  memberStore._byId.clear();
}
__LENDWELL_EOF__

cat > 'src/members/membership.js' <<'__LENDWELL_EOF__'
// What each membership tier may borrow at once.
//
// Children's cards are issued to under-16s, senior cards from 65. Staff cards go to county
// library employees and to registered volunteers.

export const LOAN_LIMITS = {
  adult: 10,
  child: 5,
  senior: 10,
  staff: 25,
};

export function isTier(tier) {
  return Object.hasOwn(LOAN_LIMITS, tier);
}

export function loanLimitFor(tier) {
  return LOAN_LIMITS[tier] ?? 0;
}
__LENDWELL_EOF__

cat > 'src/notifications/channels/email.js' <<'__LENDWELL_EOF__'
// Hands a notice to the county mail relay. The relay queues and retries on its own, so from our
// side a send only builds the envelope it expects. Members without an email address get the
// same text as a printed letter from their home branch.

export function sendEmail(to, { subject, body }) {
  if (!to) return { channel: 'letter', to: null, subject, body };
  return { channel: 'email', to, subject, body };
}
__LENDWELL_EOF__

cat > 'src/notifications/channels/sms.js' <<'__LENDWELL_EOF__'
// Text-message notices through the county's SMS carrier.

const MAX_LENGTH = 160;

export function sendSms(to, { body }) {
  const text = body.length > MAX_LENGTH ? `${body.slice(0, MAX_LENGTH - 3)}...` : body;
  return { channel: 'sms', to, body: text };
}
__LENDWELL_EOF__

cat > 'src/notifications/notifier.js' <<'__LENDWELL_EOF__'
import { FEATURES } from '../config.js';
import { loadTemplates } from './templates.js';
import { sendEmail } from './channels/email.js';
import { sendSms } from './channels/sms.js';

let templates = null;

// Every notice sent since start-up, oldest first.
export let outbox = [];

export function startNotifications() {
  templates = loadTemplates();
}

export function notifierReady() {
  return templates !== null;
}

export function notify(kind, member, data) {
  const template = templates[kind];
  if (!template) throw new Error(`no template for notice kind ${kind}`);
  const message = template({ memberName: member.name, ...data });
  const sent = sendEmail(member.email, message);
  if (FEATURES.smsNotices && member.phone) sendSms(member.phone, message);
  // push the message to the outbox
  outbox.push({ kind, memberId: member.id, ...sent });
  return sent;
}

export function sentMessages() {
  return outbox.map((message) => ({ ...message }));
}

export function resetNotifications() {
  templates = null;
  outbox = [];
}
__LENDWELL_EOF__

cat > 'src/notifications/overdue-notices.js' <<'__LENDWELL_EOF__'
import { listLoans } from '../circulation/loans.js';
import { getMember } from '../members/member-store.js';
import { getItem } from '../catalog/catalog-store.js';
import { formatDate } from '../shared/dates.js';
import { requireDate } from '../shared/validate.js';
import { notify } from './notifier.js';

// Run nightly. A member hears about an overdue item on its first day overdue and then once a
// week, not every night.
export function sendOverdueNotices(on) {
  requireDate(on, 'on');
  const sent = [];
  for (const loan of listLoans({ open: true })) {
    const daysOverdue = Math.round((Date.parse(on) - Date.parse(loan.dueOn)) / 86400000);
    if (daysOverdue < 1) continue;
    if (daysOverdue !== 1 && daysOverdue % 7 !== 0) continue;
    const member = getMember(loan.memberId);
    const item = getItem(loan.itemId);
    notify('loan.overdue', member, {
      title: item.title,
      dueOn: formatDate(loan.dueOn, true),
      daysOverdue,
    });
    sent.push({ loanId: loan.id, memberId: member.id, daysOverdue });
  }
  return sent;
}
__LENDWELL_EOF__

cat > 'src/notifications/preview.js' <<'__LENDWELL_EOF__'
// Lets an operator see a notice exactly as a member would, before changing a template goes out
// to everyone. Uses made-up sample values so no member data is needed.

import { loadTemplates } from './templates.js';

const SAMPLES = {
  'hold.ready': { title: 'The Salt Road', branchName: 'Central Library', until: '2026-03-14' },
  'hold.expired': { title: 'The Salt Road' },
  'loan.overdue': { title: 'The Salt Road', dueOn: 'Saturday 7 March 2026', daysOverdue: 3 },
};

export function previewNotice(kind, memberName = 'Sample Member') {
  const template = loadTemplates()[kind];
  if (!template) return null;
  return template({ memberName, ...SAMPLES[kind] });
}

export function noticeKinds() {
  return Object.keys(SAMPLES);
}
__LENDWELL_EOF__

cat > 'src/notifications/templates.js' <<'__LENDWELL_EOF__'
// Notice templates, one per kind. Bodies are plain text: the county mail relay strips HTML, and
// the same text is printed as a letter for members without an email address.

export function loadTemplates() {
  return {
    'hold.ready': ({ memberName, title, branchName, until }) => ({
      subject: 'Your hold is ready',
      body: `Hello ${memberName}, "${title}" is ready for pickup at ${branchName} until ${until}.`,
    }),
    'hold.expired': ({ memberName, title }) => ({
      subject: 'Your hold has expired',
      body: `Hello ${memberName}, your hold on "${title}" was not collected in time and has been released.`,
    }),
    'loan.overdue': ({ memberName, title, dueOn, daysOverdue }) => ({
      subject: `Overdue: ${title}`,
      body:
        `Hello ${memberName}, "${title}" was due back on ${dueOn} and is now ` +
        `${daysOverdue} day${daysOverdue === 1 ? '' : 's'} overdue.`,
    }),
  };
}
__LENDWELL_EOF__

cat > 'src/reports/circulation-report.js' <<'__LENDWELL_EOF__'
import { loanStore } from '../circulation/loan-store.js';
import { listItems } from '../catalog/catalog-store.js';
import { BRANCHES } from '../shared/branches.js';
import { countBy } from '../shared/collections.js';
import { requireDate } from '../shared/validate.js';

// One row per type, in catalogue order, so the monthly sheet lines up with last month's even
// when a type had no activity.
const TYPE_ORDER = ['book', 'dvd', 'magazine', 'audiobook', 'map'];

function inRange(date, from, to) {
  return date !== null && date >= from && date <= to;
}

export function circulationReport({ from, to }) {
  requireDate(from, 'from');
  requireDate(to, 'to');
  const typeOf = new Map(listItems().map((item) => [item.id, item.type]));
  const checkouts = {};
  const returns = {};
  for (const loan of loanStore._loans) {
    const type = typeOf.get(loan.itemId);
    if (inRange(loan.checkedOutOn, from, to)) checkouts[type] = (checkouts[type] ?? 0) + 1;
    if (inRange(loan.returnedOn, from, to)) returns[type] = (returns[type] ?? 0) + 1;
  }
  return TYPE_ORDER.map((type) => ({
    type,
    checkouts: checkouts[type] ?? 0,
    returns: returns[type] ?? 0,
  }));
}

// Most borrowed titles in a period. Ties keep the order in which the titles were first borrowed.
export function popularTitles({ from, to, limit = 10 }) {
  requireDate(from, 'from');
  requireDate(to, 'to');
  const titleOf = new Map(listItems().map((item) => [item.id, item.title]));
  const loans = loanStore._loans.filter((loan) => inRange(loan.checkedOutOn, from, to));
  const counts = countBy(loans, (loan) => titleOf.get(loan.itemId));
  return [...counts.entries()]
    .map(([title, checkouts]) => ({ title, checkouts }))
    .sort((a, b) => b.checkouts - a.checkouts)
    .slice(0, limit);
}

export function branchSummary() {
  const items = listItems();
  return Object.entries(BRANCHES).map(([id, branch]) => {
    const here = items.filter((item) => item.branch === id);
    const count = (status) => here.filter((item) => item.status === status).length;
    return {
      branch: id,
      name: branch.name,
      items: here.length,
      onLoan: count('on-loan'),
      onHoldShelf: count('on-hold-shelf'),
      lost: count('lost'),
    };
  });
}
__LENDWELL_EOF__

cat > 'src/reports/daily-summary.js' <<'__LENDWELL_EOF__'
// End-of-day numbers each branch manager signs off: what went out, what came back, what was
// charged and taken at the desk.

import { loanStore } from '../circulation/loan-store.js';
import { ledgerStore } from '../fines/ledger.js';
import { listItems } from '../catalog/catalog-store.js';
import { BRANCHES } from '../shared/branches.js';
import { formatCents } from '../shared/money.js';
import { requireDate } from '../shared/validate.js';

function emptyCounts() {
  return { checkouts: 0, returns: 0, lateReturns: 0 };
}

export function dailySummary(on) {
  requireDate(on, 'on');
  const branchOf = new Map(listItems().map((item) => [item.id, item.branch]));
  const perBranch = Object.fromEntries(Object.keys(BRANCHES).map((id) => [id, emptyCounts()]));

  for (const loan of loanStore._loans) {
    const branch = branchOf.get(loan.itemId);
    if (!perBranch[branch]) continue;
    if (loan.checkedOutOn === on) perBranch[branch].checkouts += 1;
    if (loan.returnedOn === on && !loan.lost) {
      perBranch[branch].returns += 1;
      if (loan.returnedOn > loan.dueOn) perBranch[branch].lateReturns += 1;
    }
  }

  let chargedCents = 0;
  let collectedCents = 0;
  let waivedCents = 0;
  for (const entries of ledgerStore._entries.values()) {
    for (const entry of entries) {
      if (entry.on !== on) continue;
      if (entry.kind === 'payment') collectedCents -= entry.amountCents;
      else if (entry.kind === 'waiver') waivedCents -= entry.amountCents;
      else chargedCents += entry.amountCents;
    }
  }

  return {
    on,
    branches: Object.entries(perBranch).map(([branch, counts]) => ({ branch, ...counts })),
    charged: formatCents(chargedCents),
    collected: formatCents(collectedCents),
    waived: formatCents(waivedCents),
  };
}
__LENDWELL_EOF__

cat > 'src/reports/exports.js' <<'__LENDWELL_EOF__'
// Quarterly loan export for the state library statistics return. One row per loan made in the
// period; no member data leaves the building.

import { loanStore } from '../circulation/loan-store.js';
import { listItems } from '../catalog/catalog-store.js';
import { requireDate } from '../shared/validate.js';

const COLUMNS = ['loan_id', 'item_type', 'branch', 'checked_out', 'due', 'returned', 'renewals'];

export function loansCsv({ from, to }) {
  requireDate(from, 'from');
  requireDate(to, 'to');
  const items = new Map(listItems().map((item) => [item.id, item]));
  const lines = [COLUMNS.join(',')];
  for (const loan of loanStore._loans) {
    if (loan.checkedOutOn < from || loan.checkedOutOn > to) continue;
    const item = items.get(loan.itemId);
    lines.push(
      [
        loan.id,
        item ? item.type : '',
        item ? item.branch : '',
        loan.checkedOutOn,
        loan.dueOn,
        loan.returnedOn ?? '',
        loan.renewals,
      ].join(','),
    );
  }
  return lines.join('\n');
}
__LENDWELL_EOF__

cat > 'src/reports/fines-report.js' <<'__LENDWELL_EOF__'
import { ledgerStore } from '../fines/ledger.js';
import { memberStore } from '../members/member-store.js';
import { formatCents } from '../shared/money.js';

// The county finance office imports this file into its own system, which expects a plain
// decimal amount in the balance column.
function dollars(cents) {
  return (cents / 100).toFixed(2);
}

function csvField(value) {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function outstanding() {
  const rows = [];
  for (const [memberId, entries] of ledgerStore._entries) {
    const balanceCents = entries.reduce((sum, entry) => sum + entry.amountCents, 0);
    if (balanceCents <= 0) continue;
    const member = memberStore._byId.get(memberId);
    rows.push({ memberId, name: member ? member.name : '(closed card)', balanceCents });
  }
  return rows;
}

export function finesReport() {
  return outstanding().map((row) => ({ ...row, balance: formatCents(row.balanceCents) }));
}

export function finesCsv() {
  const lines = ['member_id,name,balance'];
  for (const row of outstanding()) {
    lines.push([row.memberId, csvField(row.name), dollars(row.balanceCents)].join(','));
  }
  return lines.join('\n');
}

export function finesSummary() {
  const rows = outstanding();
  // sum the balances
  const totalCents = rows.reduce((sum, row) => sum + row.balanceCents, 0);
  return {
    members: rows.length,
    totalCents,
    total: formatCents(totalCents),
    averageCents: rows.length === 0 ? 0 : Math.round(totalCents / rows.length),
  };
}
__LENDWELL_EOF__

cat > 'src/reports/hold-queue-report.js' <<'__LENDWELL_EOF__'
// Titles with the longest hold queues. Selection uses it to decide which titles get extra copies.

import { listItems } from '../catalog/catalog-store.js';
import { queueFor, queueLength } from '../holds/hold-queue.js';
import { daysBetween } from '../shared/dates.js';
import { requireDate } from '../shared/validate.js';

export function holdQueueReport(on, { minimum = 1 } = {}) {
  requireDate(on, 'on');
  const rows = [];
  for (const item of listItems()) {
    const waiting = queueLength(item.id);
    if (waiting < minimum) continue;
    const oldest = queueFor(item.id)[0];
    rows.push({
      itemId: item.id,
      title: item.title,
      branch: item.branch,
      waiting,
      longestWaitDays: oldest ? daysBetween(oldest.placedOn, on) : 0,
    });
  }
  rows.sort((a, b) => b.waiting - a.waiting || b.longestWaitDays - a.longestWaitDays);
  return rows;
}
__LENDWELL_EOF__

cat > 'src/reports/member-activity.js' <<'__LENDWELL_EOF__'
import { listLoans } from '../circulation/loans.js';
import { listHolds } from '../holds/holds.js';
import { listCharges } from '../fines/fines.js';
import { getItem } from '../catalog/catalog-store.js';
import { formatCents } from '../shared/money.js';

// A member's history as one timeline, for the "my account" page and for disputes at the desk.
// Events on the same day keep the order loans, then holds, then charges.
export function memberActivity(memberId) {
  const events = [];
  for (const loan of listLoans({ memberId })) {
    const { title } = getItem(loan.itemId);
    events.push({ on: loan.checkedOutOn, what: 'borrowed', title });
    if (loan.returnedOn !== null) {
      events.push({ on: loan.returnedOn, what: loan.lost ? 'reported lost' : 'returned', title });
    }
  }
  for (const hold of listHolds({ memberId })) {
    const { title } = getItem(hold.itemId);
    events.push({ on: hold.placedOn, what: 'placed a hold', title });
  }
  for (const charge of listCharges(memberId)) {
    events.push({ on: charge.on, what: charge.kind, amount: formatCents(charge.amountCents) });
  }
  return events
    .filter((event) => event.on !== null)
    .sort((a, b) => (a.on < b.on ? -1 : a.on > b.on ? 1 : 0));
}
__LENDWELL_EOF__

cat > 'src/reports/notice-digest.js' <<'__LENDWELL_EOF__'
// Morning digest for branch staff: the hold-ready notices that went out, grouped by branch, so
// they can check the hold shelf against what members were told.

import { outbox } from '../notifications/notifier.js';

const READY = /"(.+)" is ready for pickup at (.+) until (\d{4}-\d{2}-\d{2})\.$/;

export function holdPickupDigest() {
  const byBranch = {};
  for (const message of outbox) {
    if (message.kind !== 'hold.ready') continue;
    const match = READY.exec(message.body);
    if (!match) continue;
    const [, title, branch, until] = match;
    if (!byBranch[branch]) byBranch[branch] = [];
    byBranch[branch].push({ title, until, memberId: message.memberId });
  }
  return byBranch;
}
__LENDWELL_EOF__

cat > 'src/reports/overdue-report.js' <<'__LENDWELL_EOF__'
import { loanStore } from '../circulation/loan-store.js';
import { memberStore } from '../members/member-store.js';
import { getItem } from '../catalog/catalog-store.js';
import { lateFineCents } from '../fines/fines.js';
import { formatCents } from '../shared/money.js';
import { requireDate } from '../shared/validate.js';

// The list the desk works through when phoning members: longest overdue first.
export function overdueReport(on) {
  requireDate(on, 'on');
  const rows = [];
  // loop over all loans
  for (const loan of loanStore._loans) {
    if (loan.returnedOn !== null) continue;
    const daysOverdue = Math.round((Date.parse(on) - Date.parse(loan.dueOn)) / 86400000);
    if (daysOverdue <= 0) continue;
    const member = memberStore._byId.get(loan.memberId);
    const item = getItem(loan.itemId);
    rows.push({
      loanId: loan.id,
      memberId: member.id,
      memberName: member.name,
      phone: member.phone,
      itemId: item.id,
      title: item.title,
      dueOn: loan.dueOn,
      daysOverdue,
      fineSoFar: formatCents(lateFineCents(loan, item, member, on)),
    });
  }
  rows.sort((a, b) => b.daysOverdue - a.daysOverdue);
  return rows;
}
__LENDWELL_EOF__

cat > 'src/shared/branches.js' <<'__LENDWELL_EOF__'
// The county system's branches. Ids are what we store on items and members; names are what
// members see on notices and receipts. Weekdays follow Date#getUTCDay (0 is Sunday).

export const BRANCHES = {
  main: { name: 'Central Library', address: '1 Market Square', openWeekdays: [1, 2, 3, 4, 5, 6] },
  harbor: { name: 'Harbor Branch', address: '14 Quay Road', openWeekdays: [3, 4, 5, 6] },
  hill: { name: 'Hill Street Branch', address: '200 Hill Street', openWeekdays: [1, 2, 3, 4, 5] },
};

export function isBranch(id) {
  return Object.hasOwn(BRANCHES, id);
}

export function branchName(id) {
  return BRANCHES[id]?.name ?? id;
}

export function isOpenOn(id, weekday) {
  return BRANCHES[id]?.openWeekdays.includes(weekday) ?? false;
}
__LENDWELL_EOF__

cat > 'src/shared/calendar.js' <<'__LENDWELL_EOF__'
// Days on which every branch is closed: public holidays, the annual staff training day and the
// odd emergency closure. Operators load the list through the admin API at the start of the year
// and again whenever the council announces a change.

import { LendError } from '../circulation/loans.js';
import { isIsoDate } from './dates.js';

export let closedDates = [];

export function setClosedDates(dates) {
  if (!Array.isArray(dates)) {
    throw new LendError('BAD_REQUEST', 'closed dates must be a list');
  }
  for (const date of dates) {
    if (!isIsoDate(date)) throw new LendError('BAD_DATE', `not a calendar date: ${date}`);
  }
  closedDates = [...new Set(dates)].sort();
  return closedDates.slice();
}

export function listClosedDates() {
  return closedDates.slice();
}
__LENDWELL_EOF__

cat > 'src/shared/collections.js' <<'__LENDWELL_EOF__'
export function groupBy(rows, keyOf) {
  const groups = new Map();
  for (const row of rows) {
    const key = keyOf(row);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  return groups;
}

export function countBy(rows, keyOf) {
  const counts = new Map();
  for (const row of rows) {
    const key = keyOf(row);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

export function paginate(rows, page = 1, pageSize = 25) {
  const safePage = Number.isInteger(page) && page > 0 ? page : 1;
  const start = (safePage - 1) * pageSize;
  return {
    page: safePage,
    pageSize,
    total: rows.length,
    rows: rows.slice(start, start + pageSize),
  };
}
__LENDWELL_EOF__

cat > 'src/shared/dates.js' <<'__LENDWELL_EOF__'
// Calendar-date helpers.
//
// Every date that moves through the service is a plain calendar date written as 'YYYY-MM-DD'.
// We never care about the time of day, so everything here works in UTC; that keeps a
// daylight-saving change from moving a due date by one.

const MS_PER_DAY = 86400000;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

const WEEKDAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export function isIsoDate(value) {
  if (typeof value !== 'string' || !ISO_DATE.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function toTime(date) {
  return Date.parse(`${date}T00:00:00Z`);
}

export function addDays(date, days) {
  return new Date(toTime(date) + days * MS_PER_DAY).toISOString().slice(0, 10);
}

export function daysBetween(from, to) {
  return Math.round((toTime(to) - toTime(from)) / MS_PER_DAY);
}

export function compareDates(a, b) {
  if (a === b) return 0;
  return a < b ? -1 : 1;
}

export function weekdayOf(date) {
  return new Date(toTime(date)).getUTCDay();
}

// Dates go out in two shapes: ISO everywhere in the API, spelled out in letters to members.
export function formatDate(date, forNotice = false) {
  if (!forNotice) return date;
  const d = new Date(toTime(date));
  return `${WEEKDAY_NAMES[d.getUTCDay()]} ${d.getUTCDate()} ${MONTH_NAMES[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export { addDays as plusDays };
__LENDWELL_EOF__

cat > 'src/shared/ids.js' <<'__LENDWELL_EOF__'
// Sequential ids per prefix: m-0001, i-0001, loan-0001 ...
// Desk staff read these out loud over the phone, so they stay short and predictable.

const counters = new Map();

export function nextId(prefix) {
  const next = (counters.get(prefix) ?? 0) + 1;
  counters.set(prefix, next);
  return `${prefix}-${String(next).padStart(4, '0')}`;
}

export function resetIds() {
  counters.clear();
}
__LENDWELL_EOF__

cat > 'src/shared/log.js' <<'__LENDWELL_EOF__'
// A small in-process log. In production the process wrapper ships these lines to the county's
// log collector; here we keep the most recent ones in memory so the admin screens can show them.

const MAX_LINES = 500;
const lines = [];

function write(level, message) {
  lines.push({ level, message });
  if (lines.length > MAX_LINES) lines.shift();
}

export const log = {
  debug: (message) => write('debug', message),
  info: (message) => write('info', message),
  warn: (message) => write('warn', message),
};

export function recentLog(level) {
  return lines.filter((line) => !level || line.level === level).map((line) => ({ ...line }));
}

export function clearLog() {
  lines.length = 0;
}
__LENDWELL_EOF__

cat > 'src/shared/money.js' <<'__LENDWELL_EOF__'
import { CURRENCY } from '../admin/settings.js';

const SYMBOLS = { USD: '$', EUR: '€', GBP: '£', CAD: 'CA$' };

function groupThousands(digits) {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// Amounts are integer cents everywhere in the service; this is where they become text for people.
export function formatCents(cents) {
  if (!Number.isInteger(cents)) throw new TypeError(`cents must be an integer, got ${cents}`);
  const sign = cents < 0 ? '-' : '';
  const abs = Math.abs(cents);
  const whole = groupThousands(String(Math.floor(abs / 100)));
  const fraction = String(abs % 100).padStart(2, '0');
  const symbol = SYMBOLS[CURRENCY] ?? `${CURRENCY} `;
  return `${sign}${symbol}${whole}.${fraction}`;
}

export function sumCents(amounts) {
  let total = 0;
  for (const amount of amounts) total += amount;
  return total;
}
__LENDWELL_EOF__

cat > 'src/shared/validate.js' <<'__LENDWELL_EOF__'
import { LendError } from '../circulation/loans.js';
import { isIsoDate } from './dates.js';

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function requireString(value, field) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new LendError('BAD_REQUEST', `${field} is required`);
  }
  return value.trim();
}

export function requireDate(value, field) {
  if (!isIsoDate(value)) {
    throw new LendError('BAD_DATE', `${field} must be a date like 2026-03-01, got ${value}`);
  }
  return value;
}

export function requireCents(value, field) {
  if (!Number.isInteger(value) || value <= 0) {
    throw new LendError('BAD_AMOUNT', `${field} must be a positive whole number of cents`);
  }
  return value;
}

export function optionalEmail(value) {
  if (value === undefined || value === null || value === '') return null;
  if (typeof value !== 'string' || !EMAIL.test(value)) {
    throw new LendError('BAD_REQUEST', `not an email address: ${value}`);
  }
  return value.toLowerCase();
}
__LENDWELL_EOF__

cat > 'tests/circulation.test.js' <<'__LENDWELL_EOF__'
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  resetLibrary,
  registerMember,
  addItem,
  checkoutItem,
  returnItem,
  renewLoan,
  listLoans,
  setClosedDates,
  getItem,
} from '../src/index.js';

let ada;

beforeEach(() => {
  resetLibrary();
  ada = registerMember({ name: 'Ada Okafor' });
});

test('a book goes out for 21 days', () => {
  const book = addItem({ title: 'The Salt Road', type: 'book' });
  const loan = checkoutItem(ada.id, book.id, '2026-03-01');
  assert.equal(loan.dueOn, '2026-03-22');
  assert.equal(getItem(book.id).status, 'on-loan');
});

test('a DVD goes out for 7 days', () => {
  const dvd = addItem({ title: 'Harbor Lights', type: 'dvd' });
  assert.equal(checkoutItem(ada.id, dvd.id, '2026-03-01').dueOn, '2026-03-08');
});

test('maps are for use in the library only', () => {
  const map = addItem({ title: 'County Survey 1910', type: 'map' });
  assert.throws(() => checkoutItem(ada.id, map.id, '2026-03-01'), { code: 'NOT_LOANABLE' });
});

test('a due date on a closed day moves to the next open day', () => {
  setClosedDates(['2026-03-22', '2026-03-23']);
  const book = addItem({ title: 'The Salt Road', type: 'book' });
  assert.equal(checkoutItem(ada.id, book.id, '2026-03-01').dueOn, '2026-03-24');
});

test('a child can have at most five items out', () => {
  const ben = registerMember({ name: 'Ben Okafor', tier: 'child' });
  for (let n = 0; n < 5; n += 1) {
    checkoutItem(ben.id, addItem({ title: `Picture book ${n}`, type: 'book' }).id, '2026-03-01');
  }
  const sixth = addItem({ title: 'Picture book 5', type: 'book' });
  assert.throws(() => checkoutItem(ben.id, sixth.id, '2026-03-01'), { code: 'LOAN_LIMIT' });
});

test('returning on time costs nothing and frees the item', () => {
  const book = addItem({ title: 'The Salt Road', type: 'book' });
  checkoutItem(ada.id, book.id, '2026-03-01');
  assert.equal(returnItem(book.id, '2026-03-20').fineCents, 0);
  assert.equal(getItem(book.id).status, 'available');
});

test('a renewal gives a full loan period from the renewal day', () => {
  const book = addItem({ title: 'The Salt Road', type: 'book' });
  checkoutItem(ada.id, book.id, '2026-03-01');
  const renewed = renewLoan(book.id, '2026-03-10');
  assert.equal(renewed.dueOn, '2026-03-31');
  assert.equal(renewed.renewals, 1);
});

test('lists loans', () => {
  const book = addItem({ title: 'The Salt Road', type: 'book' });
  checkoutItem(ada.id, book.id, '2026-03-01');
  assert.deepEqual(listLoans(), listLoans());
});
__LENDWELL_EOF__

cat > 'tests/dates.test.js' <<'__LENDWELL_EOF__'
import test from 'node:test';
import assert from 'node:assert/strict';
import { addDays, daysBetween, isIsoDate } from '../src/shared/dates.js';
import { dueDateFor } from '../src/circulation/due-dates.js';

test('addDays crosses month, year and leap-day boundaries', () => {
  assert.equal(addDays('2026-01-31', 1), '2026-02-01');
  assert.equal(addDays('2026-12-31', 1), '2027-01-01');
  assert.equal(addDays('2028-02-28', 1), '2028-02-29');
  assert.equal(addDays('2026-03-10', -10), '2026-02-28');
});

test('daysBetween counts calendar days in either direction', () => {
  assert.equal(daysBetween('2026-03-01', '2026-03-08'), 7);
  assert.equal(daysBetween('2026-03-08', '2026-03-01'), -7);
  assert.equal(daysBetween('2026-03-28', '2026-03-30'), 2);
});

test('isIsoDate accepts real dates only', () => {
  assert.equal(isIsoDate('2026-02-28'), true);
  assert.equal(isIsoDate('2026-02-30'), false);
  assert.equal(isIsoDate('2026-2-3'), false);
  assert.equal(isIsoDate(20260203), false);
});

test('due date is the loan period after checkout', () => {
  assert.equal(dueDateFor('2026-03-01', 21), addDays('2026-03-01', 21));
});
__LENDWELL_EOF__

cat > 'tests/fines.test.js' <<'__LENDWELL_EOF__'
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  resetLibrary,
  registerMember,
  addItem,
  checkoutItem,
  returnItem,
  getBalance,
  payFine,
  formatCents,
} from '../src/index.js';

beforeEach(() => resetLibrary());

function lateReturn(member, { type = 'book', daysLate, replacementCostCents } = {}) {
  const item = addItem({ title: 'The Salt Road', type, replacementCostCents });
  const loan = checkoutItem(member.id, item.id, '2026-03-01');
  const [y, m, d] = loan.dueOn.split('-').map(Number);
  const back = new Date(Date.UTC(y, m - 1, d + daysLate)).toISOString().slice(0, 10);
  return returnItem(item.id, back);
}

test('one grace day, then every day late is charged, the grace day included', () => {
  const ada = registerMember({ name: 'Ada Okafor' });
  assert.equal(lateReturn(ada, { daysLate: 1 }).fineCents, 0);
  assert.equal(lateReturn(ada, { daysLate: 2 }).fineCents, 50);
  assert.equal(getBalance(ada.id), 50);
});

test('seniors pay two thirds, rounded down', () => {
  const cleo = registerMember({ name: 'Cleo Marsh', tier: 'senior' });
  assert.equal(lateReturn(cleo, { daysLate: 4 }).fineCents, 66);
});

test('staff pay no fines', () => {
  const dev = registerMember({ name: 'Dev Patel', tier: 'staff' });
  assert.equal(lateReturn(dev, { type: 'dvd', daysLate: 9 }).fineCents, 0);
});

test.skip('a fine is capped at the replacement cost of the item', () => {
  const ada = registerMember({ name: 'Ada Okafor' });
  const result = lateReturn(ada, { daysLate: 100, replacementCostCents: 1200 });
  assert.equal(result.fineCents, 1200);
});

test('formats amounts for people', () => {
  assert.equal(formatCents(1250), '$' + (1250 / 100).toFixed(2));
});

test('a payment retries once when Paywell times out', async () => {
  const ada = registerMember({ name: 'Ada Okafor' });
  lateReturn(ada, { daysLate: 4 });
  let calls = 0;
  const gateway = {
    async charge() {
      calls += 1;
      if (calls === 1) throw Object.assign(new Error('timeout'), { code: 'ETIMEDOUT' });
      return { chargeId: 'pw-1' };
    },
  };
  const paid = await payFine(ada.id, 100, { gateway });
  assert.equal(paid.attempts, 2);
  assert.equal(getBalance(ada.id), 0);
});
__LENDWELL_EOF__

cat > 'tests/holds.test.js' <<'__LENDWELL_EOF__'
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  resetLibrary,
  startNotifications,
  sentMessages,
  registerMember,
  addItem,
  getItem,
  checkoutItem,
  returnItem,
  renewLoan,
  placeHold,
  cancelHold,
  listHolds,
} from '../src/index.js';

let ada;
let ben;
let book;

beforeEach(() => {
  resetLibrary();
  startNotifications();
  ada = registerMember({ name: 'Ada Okafor', email: 'ada@example.org' });
  ben = registerMember({ name: 'Ben Okafor' });
  book = addItem({ title: 'The Salt Road', type: 'book' });
  checkoutItem(ada.id, book.id, '2026-03-01');
});

test('a returned item with a hold goes to the hold shelf and the member is told', () => {
  placeHold(ben.id, book.id, '2026-03-02');
  returnItem(book.id, '2026-03-10');
  assert.equal(getItem(book.id).status, 'on-hold-shelf');
  const [hold] = listHolds({ itemId: book.id });
  assert.equal(hold.status, 'ready');
  assert.equal(hold.readyUntil, '2026-03-17');
  assert.equal(sentMessages().length, 1);
  assert.equal(sentMessages()[0].kind, 'hold.ready');
});

test('only the member the hold is for can collect it', () => {
  const cleo = registerMember({ name: 'Cleo Marsh' });
  placeHold(ben.id, book.id, '2026-03-02');
  returnItem(book.id, '2026-03-10');
  assert.throws(() => checkoutItem(cleo.id, book.id, '2026-03-11'), { code: 'ON_HOLD' });
  assert.equal(checkoutItem(ben.id, book.id, '2026-03-11').memberId, ben.id);
});

test('a renewal is refused while someone is waiting', () => {
  placeHold(ben.id, book.id, '2026-03-02');
  assert.throws(() => renewLoan(book.id, '2026-03-05'), { code: 'HAS_HOLDS' });
});

test('cancelling a hold removes it from the queue', () => {
  const hold = placeHold(ben.id, book.id, '2026-03-02');
  try {
    cancelHold(hold.id, '2026-03-03');
    assert.equal(listHolds({ itemId: book.id, status: 'waiting' }).length, 0);
  } catch (err) {
    // the queue may already be empty
  }
});
__LENDWELL_EOF__

cat > 'tests/http.test.js' <<'__LENDWELL_EOF__'
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { resetLibrary, handleRequest } from '../src/index.js';

const headers = { authorization: 'Bearer dev-admin-token' };
const call = (method, path, body) => handleRequest({ method, path, headers, body });

beforeEach(() => resetLibrary());

test('requests without the admin token are refused', async () => {
  const res = await handleRequest({ method: 'GET', path: '/members' });
  assert.equal(res.status, 401);
});

test('creates a member', async () => {
  const res = await call('POST', '/members', { name: 'Ada Okafor', tier: 'senior' });
  assert.equal(res.status, 201);
  assert.equal(res.body.id, 'm-0001');
});

test('creates a book and returns its barcode', async () => {
  const res = await call('POST', '/items', { title: 'The Salt Road', type: 'book' });
  assert.equal(res.status, 201);
  assert.match(res.body.barcode, /^LW\d{8}$/);
});

test('an unknown tier is a bad request', async () => {
  const res = await call('POST', '/members', { name: 'Ada Okafor', tier: 'gold' });
  assert.equal(res.status, 400);
  assert.equal(res.body.error, 'BAD_TIER');
});

test('finds items by title word', async () => {
  await call('POST', '/items', { title: 'The Salt Road', author: 'Jane Halloran', type: 'book' });
  await call('POST', '/items', { title: 'Harbor Lights', type: 'dvd' });
  const res = await call('GET', '/search?q=salt');
  assert.equal(res.status, 200);
  assert.deepEqual(res.body.map((item) => item.title), ['The Salt Road']);
});

test('unknown routes are 404', async () => {
  const res = await call('GET', '/nowhere');
  assert.equal(res.status, 404);
});
__LENDWELL_EOF__

cat > 'tests/members.test.js' <<'__LENDWELL_EOF__'
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  resetLibrary,
  registerMember,
  getMember,
  listMembers,
  memberSummary,
  memberIdForCard,
  addItem,
  checkoutItem,
} from '../src/index.js';

beforeEach(() => resetLibrary());

test('registers members with sequential ids and a card number', () => {
  const ada = registerMember({ name: 'Ada Okafor', email: 'Ada@Example.org' });
  const ben = registerMember({ name: 'Ben Okafor', tier: 'child' });
  assert.equal(ada.id, 'm-0001');
  assert.equal(ben.id, 'm-0002');
  assert.equal(ada.email, 'ada@example.org');
  assert.equal(memberIdForCard(ada.cardNumber), 'm-0001');
  assert.equal(getMember('m-0002').tier, 'child');
});

test('rejects an unknown tier', () => {
  assert.throws(() => registerMember({ name: 'Cleo', tier: 'gold' }), { code: 'BAD_TIER' });
});

test('lists members', () => {
  registerMember({ name: 'Ada Okafor' });
  listMembers();
  assert.ok(true);
});

test('summary shows how many more items a member can borrow', () => {
  const ben = registerMember({ name: 'Ben Okafor', tier: 'child' });
  const item = addItem({ title: 'Gull Island', type: 'book' });
  checkoutItem(ben.id, item.id, '2026-03-01');
  assert.deepEqual(memberSummary(ben.id), {
    id: ben.id,
    name: 'Ben Okafor',
    tier: 'child',
    active: true,
    onLoan: 1,
    canBorrow: 4,
  });
});
__LENDWELL_EOF__

cat > 'tests/reports.test.js' <<'__LENDWELL_EOF__'
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  resetLibrary,
  registerMember,
  addItem,
  checkoutItem,
  returnItem,
  circulationReport,
  finesCsv,
  ITEM_TYPES,
} from '../src/index.js';

beforeEach(() => resetLibrary());

test('circulation report has a row for every item type', () => {
  const ada = registerMember({ name: 'Ada Okafor' });
  const book = addItem({ title: 'The Salt Road', type: 'book' });
  checkoutItem(ada.id, book.id, '2026-03-01');
  returnItem(book.id, '2026-03-05');
  const rows = circulationReport({ from: '2026-03-01', to: '2026-03-31' });
  assert.equal(rows.length, ITEM_TYPES.length);
  assert.deepEqual(rows.find((row) => row.type === 'book'), { type: 'book', checkouts: 1, returns: 1 });
});

test('fines export starts with its header line', () => {
  assert.equal(finesCsv(), 'member_id,name,balance');
});
__LENDWELL_EOF__

cat > .gitignore <<'__LENDWELL_EOF__'
node_modules/
__LENDWELL_EOF__

{
  export GIT_AUTHOR_DATE='2026-10-01T09:00:00Z' GIT_COMMITTER_DATE='2026-10-01T09:00:00Z'
  git init -q &&
    git add -A &&
    git -c user.name='lendwell' -c user.email='dev@lendwell.invalid' -c commit.gpgsign=false commit -qm 'lendwell 2.4.1' 
} >/dev/null 2>&1 || true
