#!/usr/bin/env bash
# A reference restructure of the lendwell fixture, used by selfcheck.sh to show that a correct,
# complete fix scores full marks. Run it inside a directory written by fixture.sh. It only writes
# files (like the agent under test, it cannot delete); files nothing imports any more stay on disk.
set -euo pipefail

mkdir -p 'src/admin'
cat > 'src/admin/auth.js' <<'__LENDWELL_REF_EOF__'
import { ADMIN_TOKEN } from '../config.js';

export function isAuthorised(headers = {}) {
  const value = headers.authorization ?? headers.Authorization ?? '';
  return value === `Bearer ${ADMIN_TOKEN}`;
}
__LENDWELL_REF_EOF__

mkdir -p 'src/admin'
cat > 'src/admin/handlers.js' <<'__LENDWELL_REF_EOF__'
import { LendError } from '../shared/errors.js';
import { checkoutItem, returnItem, renewLoan, findLoan, markItemLost } from '../circulation/loans.js';
import { createMember, listMembers, findMembersByName } from '../members/member-store.js';
import { memberSummary, deactivateMember, changeTier } from '../members/member-service.js';
import { isTier, TIER_NAMES } from '../members/membership.js';
import { addItem, getItem, updateItem, withdrawItem } from '../catalog/catalog-store.js';
import { isItemType, ITEM_TYPES } from '../catalog/item-types.js';
import { toBarcode } from '../catalog/barcodes.js';
import { searchCatalog } from '../catalog/search.js';
import { placeHold, cancelHold, listHolds, expireHolds } from '../holds/holds.js';
import { getBalance, listCharges, waiveFine } from '../fines/fines.js';
import { setClosedDates, listClosedDates } from '../shared/calendar.js';
import { paginate } from '../shared/collections.js';
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
import { DEFAULT_PAGE_SIZE } from '../config.js';


const ok = (body) => ({ status: 200, body });
const created = (body) => ({ status: 201, body });

// ---- members ---------------------------------------------------------------

export function postMember({ body }) {
  if (body.tier !== undefined && !isTier(body.tier)) {
    throw new LendError('BAD_TIER', `tier must be one of ${TIER_NAMES.join(', ')}`);
  }
  return created(createMember(body));
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
  if (!isTier(body.tier)) {
    throw new LendError('BAD_TIER', `tier must be one of ${TIER_NAMES.join(', ')}`);
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
  if (!isItemType(body.type)) {
    throw new LendError('BAD_TYPE', `type must be one of ${ITEM_TYPES.join(', ')}`);
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
__LENDWELL_REF_EOF__

mkdir -p 'src/admin'
cat > 'src/admin/http.js' <<'__LENDWELL_REF_EOF__'
// A tiny router for the operator screens. The desk app's server forwards requests here as plain
// objects ({ method, path, headers, body }) and writes back whatever we return.

import { LendError } from '../shared/errors.js';
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

export async function handleRequest({ method = 'GET', path = '/', headers = {}, body = {} } = {}) {
  if (!isAuthorised(headers)) return { status: 401, body: { error: 'UNAUTHORISED' } };
  const { pathname, query } = splitPath(path);
  for (const [verb, pattern, handler] of ROUTES) {
    if (verb !== method) continue;
    const params = matchRoute(pattern, pathname);
    if (!params) continue;
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
__LENDWELL_REF_EOF__

mkdir -p 'src/catalog'
cat > 'src/catalog/catalog-store.js' <<'__LENDWELL_REF_EOF__'
import { LendError } from '../shared/errors.js';
import { nextId } from '../shared/ids.js';
import { isBranch } from '../shared/branches.js';
import { requireString } from '../shared/validate.js';
import { isItemType } from './item-types.js';

// What we charge for a lost item when cataloguing did not record a price.
const DEFAULT_REPLACEMENT_CENTS = 2000;

const STATUSES = ['available', 'on-loan', 'on-hold-shelf', 'lost', 'withdrawn'];

const items = new Map();

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
  items.set(item.id, item);
  return { ...item };
}

export function findItem(id) {
  const item = items.get(id);
  return item ? { ...item } : undefined;
}

export function getItem(id) {
  const item = items.get(id);
  if (!item) throw new LendError('NO_ITEM', `no item ${id}`);
  return { ...item };
}

export function listItems() {
  return [...items.values()].map((item) => ({ ...item }));
}

export function setItemStatus(id, status) {
  if (!STATUSES.includes(status)) throw new Error(`unknown item status ${status}`);
  const item = items.get(id);
  if (!item) throw new LendError('NO_ITEM', `no item ${id}`);
  item.status = status;
  return { ...item };
}

const EDITABLE = ['title', 'author', 'year', 'branch', 'replacementCostCents'];

// Cataloguing fixes: typos in titles, a transfer to another branch, a new price from the supplier.
export function updateItem(id, changes) {
  const item = items.get(id);
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
  return { ...item };
}

// Weeded items stay in the catalogue so old loans still resolve, but can no longer circulate.
export function withdrawItem(id) {
  const item = items.get(id);
  if (!item) throw new LendError('NO_ITEM', `no item ${id}`);
  if (item.status !== 'available') {
    throw new LendError('NOT_AVAILABLE', `${item.title} is ${item.status} and cannot be withdrawn`);
  }
  return setItemStatus(id, 'withdrawn');
}

export function resetCatalog() {
  items.clear();
}
__LENDWELL_REF_EOF__

mkdir -p 'src/catalog'
cat > 'src/catalog/item-types.js' <<'__LENDWELL_REF_EOF__'
// Kinds of thing the library holds. Maps are reference-only: they have no loan period.

const TYPES = {
  book: { loanDays: 21, finePerDayCents: 25 },
  dvd: { loanDays: 7, finePerDayCents: 100 },
  magazine: { loanDays: 7, finePerDayCents: 10 },
  audiobook: { loanDays: 14, finePerDayCents: 50 },
  map: { loanDays: null, finePerDayCents: 0 },
};

export const ITEM_TYPES = Object.keys(TYPES);

export function isItemType(type) {
  return Object.hasOwn(TYPES, type);
}

export function isLoanable(type) {
  return TYPES[type]?.loanDays != null;
}

export function loanDaysFor(type) {
  const days = TYPES[type]?.loanDays;
  if (days == null) throw new Error(`no loan period for ${type}`);
  return days;
}

export function finePerDayFor(type) {
  return TYPES[type]?.finePerDayCents ?? 0;
}
__LENDWELL_REF_EOF__

mkdir -p 'src/catalog'
cat > 'src/catalog/search.js' <<'__LENDWELL_REF_EOF__'
// Title and author search over the catalogue.

import { listItems } from './catalog-store.js';

function tokenize(text) {
  return String(text)
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
}

export function searchCatalog(query, { type, branch, availableOnly = false } = {}) {
  const terms = tokenize(query);
  if (terms.length === 0) return [];
  const scored = [];
  for (const item of listItems()) {
    const words = new Set(tokenize(`${item.title} ${item.author}`));
    const hits = terms.filter((term) => words.has(term)).length;
    if (hits === 0 || item.status === 'withdrawn') continue;
    if (type && item.type !== type) continue;
    if (branch && item.branch !== branch) continue;
    if (availableOnly && item.status !== 'available') continue;
    scored.push({ item, hits });
  }
  scored.sort((a, b) => b.hits - a.hits);
  return scored.map(({ item }) => item);
}
__LENDWELL_REF_EOF__

mkdir -p 'src/circulation'
cat > 'src/circulation/due-dates.js' <<'__LENDWELL_REF_EOF__'
import { addDays } from '../shared/dates.js';
import { isClosed } from '../shared/calendar.js';

// A due date never lands on a day the whole system is closed; it moves to the next open day.
export function dueDateFor(start, loanDays) {
  let due = addDays(start, loanDays);
  while (isClosed(due)) due = addDays(due, 1);
  return due;
}
__LENDWELL_REF_EOF__

mkdir -p 'src/circulation'
cat > 'src/circulation/loan-policy.js' <<'__LENDWELL_REF_EOF__'
export const MAX_RENEWALS = 2;
__LENDWELL_REF_EOF__

mkdir -p 'src/circulation'
cat > 'src/circulation/loan-store.js' <<'__LENDWELL_REF_EOF__'
// Every loan, open and closed, in the order the loans were made.

const loans = [];

export function addLoan(loan) {
  loans.push(loan);
  return loan;
}

export function openLoanForItem(itemId) {
  return loans.find((loan) => loan.itemId === itemId && loan.returnedOn === null);
}

export function loansForMember(memberId) {
  return loans.filter((loan) => loan.memberId === memberId);
}

export function allLoans() {
  return loans.map((loan) => ({ ...loan }));
}

export function resetLoans() {
  loans.length = 0;
}
__LENDWELL_REF_EOF__

mkdir -p 'src/circulation'
cat > 'src/circulation/loans.js' <<'__LENDWELL_REF_EOF__'
import { LendError } from '../shared/errors.js';
import { nextId } from '../shared/ids.js';
import { requireDate } from '../shared/validate.js';
import { getMember } from '../members/member-store.js';
import { loanLimitFor } from '../members/membership.js';
import { getItem, setItemStatus } from '../catalog/catalog-store.js';
import { isLoanable, loanDaysFor } from '../catalog/item-types.js';
import { chargeLateFine, getBalance } from '../fines/fines.js';
import { BLOCK_THRESHOLD_CENTS } from '../fines/fine-rates.js';
import { addEntry } from '../fines/ledger.js';
import { readyHoldFor, hasWaitingHold, collectHold, promoteNextHold } from '../holds/holds.js';
import { addLoan, openLoanForItem, loansForMember, allLoans } from './loan-store.js';
import { MAX_RENEWALS } from './loan-policy.js';
import { dueDateFor } from './due-dates.js';

export function openLoansFor(memberId) {
  return loansForMember(memberId).filter((loan) => loan.returnedOn === null).map((loan) => ({ ...loan }));
}

export function findLoan(itemId) {
  const loan = openLoanForItem(itemId);
  return loan ? { ...loan } : undefined;
}

export function listLoans({ memberId, open } = {}) {
  return allLoans()
    .filter((loan) => memberId === undefined || loan.memberId === memberId)
    .filter((loan) => open === undefined || (loan.returnedOn === null) === open);
}

export function checkoutItem(memberId, itemId, on) {
  requireDate(on, 'on');
  const member = getMember(memberId);
  const item = getItem(itemId);
  if (!member.active) throw new LendError('MEMBER_INACTIVE', `${member.name}'s card is closed`);
  if (!isLoanable(item.type)) throw new LendError('NOT_LOANABLE', `${item.title} is for use in the library only`);
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
  if (hold) collectHold(itemId);
  const loan = {
    id: nextId('loan'),
    memberId,
    itemId,
    checkedOutOn: on,
    dueOn: dueDateFor(on, loanDaysFor(item.type)),
    renewals: 0,
    returnedOn: null,
  };
  addLoan(loan);
  setItemStatus(itemId, 'on-loan');
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
  promoteNextHold(itemId, on);
  return { ...loan, fineCents };
}

export function renewLoan(itemId, on) {
  requireDate(on, 'on');
  const loan = openLoanForItem(itemId);
  if (!loan) throw new LendError('NOT_ON_LOAN', `${itemId} is not on loan`);
  if (loan.renewals >= MAX_RENEWALS) {
    throw new LendError('RENEWAL_LIMIT', `${itemId} has already been renewed ${loan.renewals} times`);
  }
  if (hasWaitingHold(itemId)) throw new LendError('HAS_HOLDS', `another member is waiting for ${itemId}`);
  loan.dueOn = dueDateFor(on, loanDaysFor(getItem(itemId).type));
  loan.renewals += 1;
  return { ...loan };
}

// The desk marks an item lost when the borrower reports it, or after 60 days overdue. The loan
// is closed and the borrower is charged the replacement cost.
export function markItemLost(itemId, on) {
  const item = getItem(itemId);
  const loan = openLoanForItem(itemId);
  if (!loan) throw new LendError('NOT_ON_LOAN', `${itemId} is not on loan`);
  loan.returnedOn = on;
  loan.lost = true;
  setItemStatus(itemId, 'lost');
  addEntry(loan.memberId, { kind: 'replacement', amountCents: item.replacementCostCents, on, note: item.title });
  return { itemId, memberId: loan.memberId, chargedCents: item.replacementCostCents };
}
__LENDWELL_REF_EOF__

mkdir -p 'src'
cat > 'src/config.js' <<'__LENDWELL_REF_EOF__'
// Settings, read once from the environment when the service starts.

export const MAX_HOLDS_PER_MEMBER = parseInt(process.env.LENDWELL_MAX_HOLDS, 10) || 5;

export const CURRENCY = process.env.LENDWELL_CURRENCY || 'USD';

export const ADMIN_TOKEN = process.env.LENDWELL_ADMIN_TOKEN || 'dev-admin-token';

export const DEFAULT_PAGE_SIZE = 25;
__LENDWELL_REF_EOF__

mkdir -p 'src/fines'
cat > 'src/fines/fine-rates.js' <<'__LENDWELL_REF_EOF__'
// Days after the due date before any fine is owed.
export const GRACE_DAYS = 1;

// Members who owe more than this cannot borrow.
export const BLOCK_THRESHOLD_CENTS = 1000;
__LENDWELL_REF_EOF__

mkdir -p 'src/fines'
cat > 'src/fines/fines.js' <<'__LENDWELL_REF_EOF__'
import { LendError } from '../shared/errors.js';
import { daysBetween } from '../shared/dates.js';
import { requireCents, requireString } from '../shared/validate.js';
import { getMember } from '../members/member-store.js';
import { applyFineShare } from '../members/membership.js';
import { getItem } from '../catalog/catalog-store.js';
import { finePerDayFor } from '../catalog/item-types.js';
import { GRACE_DAYS } from './fine-rates.js';
import { addEntry, balanceFor, entriesFor } from './ledger.js';

export function lateFineCents(loan, item, member, returnedOn) {
  const daysLate = daysBetween(loan.dueOn, returnedOn);
  // Inside the grace period nothing is owed. Past it, the grace day is charged with the rest
  // (circulation policy 4.2), so an item two days late costs two days.
  if (daysLate <= GRACE_DAYS) return 0;
  // A fine never exceeds what it would cost to replace the item.
  const total = Math.min(daysLate * finePerDayFor(item.type), item.replacementCostCents);
  return applyFineShare(member.tier, total);
}

export function chargeLateFine(loan, returnedOn) {
  const item = getItem(loan.itemId);
  const member = getMember(loan.memberId);
  const amountCents = lateFineCents(loan, item, member, returnedOn);
  if (amountCents > 0) {
    addEntry(member.id, { kind: 'late', amountCents, on: returnedOn, note: `${item.title}, due ${loan.dueOn}` });
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
  if (amountCents > owed) throw new LendError('OVER_WAIVE', `cannot waive ${amountCents} cents, ${memberId} owes ${owed}`);
  return addEntry(memberId, { kind: 'waiver', amountCents: -amountCents, on, note: why });
}
__LENDWELL_REF_EOF__

mkdir -p 'src/fines'
cat > 'src/fines/ledger.js' <<'__LENDWELL_REF_EOF__'
// Charges and credits per member. Positive amounts are owed by the member; payments and
// waivers are stored as negative amounts.

import { nextId } from '../shared/ids.js';

const byMember = new Map();

export function addEntry(memberId, { kind, amountCents, on = null, note = '' }) {
  if (!byMember.has(memberId)) byMember.set(memberId, []);
  const entry = { id: nextId('fee'), memberId, kind, amountCents, on, note };
  byMember.get(memberId).push(entry);
  return { ...entry };
}

export function entriesFor(memberId) {
  return (byMember.get(memberId) ?? []).map((entry) => ({ ...entry }));
}

export function balanceFor(memberId) {
  return (byMember.get(memberId) ?? []).reduce((sum, entry) => sum + entry.amountCents, 0);
}

// Every member with ledger entries, in the order they first got one.
export function balancesByMember() {
  return [...byMember.entries()].map(([memberId, entries]) => ({
    memberId,
    balanceCents: entries.reduce((sum, entry) => sum + entry.amountCents, 0),
  }));
}

export function allEntries() {
  return [...byMember.values()].flat().map((entry) => ({ ...entry }));
}

export function resetLedger() {
  byMember.clear();
}
__LENDWELL_REF_EOF__

mkdir -p 'src/fines'
cat > 'src/fines/payments.js' <<'__LENDWELL_REF_EOF__'
// Card payments for fines, through Paywell.

import { LendError } from '../shared/errors.js';
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
__LENDWELL_REF_EOF__

mkdir -p 'src/holds'
cat > 'src/holds/holds.js' <<'__LENDWELL_REF_EOF__'
import { MAX_HOLDS_PER_MEMBER } from '../config.js';
import { LendError } from '../shared/errors.js';
import { nextId } from '../shared/ids.js';
import { addDays } from '../shared/dates.js';
import { branchName, holdShelfDaysFor } from '../shared/branches.js';
import { requireDate } from '../shared/validate.js';
import { openLoanForItem } from '../circulation/loan-store.js';
import { getMember } from '../members/member-store.js';
import { getItem, setItemStatus } from '../catalog/catalog-store.js';
import { notify } from '../notifications/notifier.js';

// Every hold ever placed, in order; each item's queue holds its live ones, oldest first.
const holds = [];
const queues = new Map();
const LIVE = ['waiting', 'ready'];

function queueOf(itemId) {
  if (!queues.has(itemId)) queues.set(itemId, []);
  return queues.get(itemId);
}

function dequeue(hold) {
  const queue = queueOf(hold.itemId);
  const at = queue.indexOf(hold);
  if (at >= 0) queue.splice(at, 1);
}

export function readyHoldFor(itemId) {
  return queueOf(itemId).find((hold) => hold.status === 'ready');
}

export function hasWaitingHold(itemId) {
  return queueOf(itemId).some((hold) => hold.status === 'waiting');
}

export function collectHold(itemId) {
  const hold = readyHoldFor(itemId);
  hold.status = 'collected';
  dequeue(hold);
}

export function holdQueue(itemId) {
  return queueOf(itemId).map((hold) => ({ ...hold }));
}

// Hands the item to the next waiting member, who is told, or puts it back on the open shelf.
export function promoteNextHold(itemId, on) {
  const item = getItem(itemId);
  const next = queueOf(itemId).find((hold) => hold.status === 'waiting');
  if (!next) {
    setItemStatus(itemId, 'available');
    return null;
  }
  next.status = 'ready';
  next.readyOn = on;
  next.readyUntil = addDays(on, holdShelfDaysFor(item.branch));
  setItemStatus(itemId, 'on-hold-shelf');
  notify('hold.ready', getMember(next.memberId), { title: item.title, branchName: branchName(item.branch), until: next.readyUntil });
  return { ...next };
}

export function placeHold(memberId, itemId, on) {
  requireDate(on, 'on');
  const member = getMember(memberId);
  const item = getItem(itemId);
  if (!member.active) throw new LendError('MEMBER_INACTIVE', `${member.name}'s card is closed`);
  if (item.status === 'available') throw new LendError('ITEM_AVAILABLE', `${item.title} is on the shelf; borrow it instead`);
  if (item.status === 'lost' || item.status === 'withdrawn') throw new LendError('NOT_AVAILABLE', `${item.title} is ${item.status}`);
  const loan = openLoanForItem(itemId);
  if (loan && loan.memberId === memberId) throw new LendError('ALREADY_BORROWED', `${member.name} has ${item.title} on loan already`);
  const mine = holds.filter((hold) => hold.memberId === memberId && LIVE.includes(hold.status));
  if (mine.some((hold) => hold.itemId === itemId)) throw new LendError('DUPLICATE_HOLD', `${member.name} already has a hold on ${item.title}`);
  if (mine.length >= MAX_HOLDS_PER_MEMBER) throw new LendError('HOLD_LIMIT', `${member.name} already has ${mine.length} holds`);
  const hold = { id: nextId('h'), memberId, itemId, placedOn: on, status: 'waiting', readyOn: null, readyUntil: null };
  holds.push(hold);
  queueOf(itemId).push(hold);
  return { ...hold, position: queueOf(itemId).length };
}

export function cancelHold(holdId, on) {
  requireDate(on, 'on');
  const hold = holds.find((h) => h.id === holdId);
  if (!hold) throw new LendError('NO_HOLD', `no hold ${holdId}`);
  if (!LIVE.includes(hold.status)) throw new LendError('HOLD_CLOSED', `${holdId} is already ${hold.status}`);
  const wasOnShelf = hold.status === 'ready';
  hold.status = 'cancelled';
  dequeue(hold);
  if (wasOnShelf) promoteNextHold(hold.itemId, on);
  return { ...hold };
}

export function listHolds({ memberId, itemId, status } = {}) {
  return holds
    .filter((hold) => memberId === undefined || hold.memberId === memberId)
    .filter((hold) => itemId === undefined || hold.itemId === itemId)
    .filter((hold) => status === undefined || hold.status === status)
    .map((hold) => ({ ...hold }));
}

// Run every morning: a hold not collected by the end of its last shelf day moves on.
export function expireHolds(on) {
  requireDate(on, 'on');
  const expired = [];
  for (const hold of holds) {
    if (hold.status !== 'ready' || on <= hold.readyUntil) continue;
    const item = getItem(hold.itemId);
    hold.status = 'expired';
    dequeue(hold);
    notify('hold.expired', getMember(hold.memberId), { title: item.title });
    promoteNextHold(hold.itemId, on);
    expired.push({ ...hold });
  }
  return expired;
}

export function resetHolds() {
  holds.length = 0;
  queues.clear();
}
__LENDWELL_REF_EOF__

mkdir -p 'src'
cat > 'src/index.js' <<'__LENDWELL_REF_EOF__'
// Public entry point of the lending service. The desk app, the kiosks and the member app import
// from here and nowhere else.

import { resetMembers } from './members/member-store.js';
import { resetCatalog } from './catalog/catalog-store.js';
import { resetLoans } from './circulation/loan-store.js';
import { resetHolds } from './holds/holds.js';
import { resetLedger } from './fines/ledger.js';
import { resetNotifications } from './notifications/notifier.js';
import { setClosedDates } from './shared/calendar.js';
import { resetIds } from './shared/ids.js';
import { clearLog } from './shared/log.js';

export { createMember as registerMember, getMember, findMember, listMembers } from './members/member-store.js';
export { memberSummary, deactivateMember, changeTier, updateContact } from './members/member-service.js';
export { memberIdForCard } from './members/cards.js';
export { addItem, getItem, findItem, listItems, updateItem, withdrawItem } from './catalog/catalog-store.js';
export { ITEM_TYPES } from './catalog/item-types.js';
export { searchCatalog } from './catalog/search.js';
export { parseBarcode, toBarcode } from './catalog/barcodes.js';
export { LendError } from './shared/errors.js';
export { checkoutItem, returnItem, renewLoan, findLoan, listLoans, markItemLost } from './circulation/loans.js';
export { placeHold, cancelHold, listHolds, expireHolds } from './holds/holds.js';
export { getBalance, listCharges, waiveFine } from './fines/fines.js';
export { payFine } from './fines/payments.js';
export { memberStatement, statementText } from './fines/statements.js';
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
  resetLoans();
  resetHolds();
  resetLedger();
  resetNotifications();
  setClosedDates([]);
  resetIds();
  clearLog();
}
__LENDWELL_REF_EOF__

mkdir -p 'src/members'
cat > 'src/members/member-service.js' <<'__LENDWELL_REF_EOF__'
// Member operations that need to know about loans.

import { loansForMember } from '../circulation/loan-store.js';
import { LendError } from '../shared/errors.js';
import { getMember, setActive, updateMember } from './member-store.js';
import { loanLimitFor } from './membership.js';

const openLoanCount = (memberId) => loansForMember(memberId).filter((loan) => loan.returnedOn === null).length;

export function deactivateMember(id) {
  const member = getMember(id);
  const open = openLoanCount(id);
  if (open > 0) throw new LendError('HAS_LOANS', `${member.name} still has ${open} item(s) on loan`);
  return setActive(id, false);
}

export function memberSummary(id) {
  const member = getMember(id);
  const onLoan = openLoanCount(id);
  return {
    id: member.id,
    name: member.name,
    tier: member.tier,
    active: member.active,
    onLoan,
    canBorrow: member.active ? Math.max(0, loanLimitFor(member.tier) - onLoan) : 0,
  };
}

export function changeTier(id, tier) {
  return updateMember(id, { tier });
}

export function updateContact(id, { email, phone }) {
  const changes = {};
  if (email !== undefined) changes.email = email;
  if (phone !== undefined) changes.phone = phone;
  return updateMember(id, changes);
}
__LENDWELL_REF_EOF__

mkdir -p 'src/members'
cat > 'src/members/member-store.js' <<'__LENDWELL_REF_EOF__'
import { LendError } from '../shared/errors.js';
import { nextId } from '../shared/ids.js';
import { isBranch } from '../shared/branches.js';
import { requireString, optionalEmail } from '../shared/validate.js';
import { isTier } from './membership.js';
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

export function setActive(id, active) {
  const member = memberStore._byId.get(id);
  if (!member) throw new LendError('NO_MEMBER', `no member ${id}`);
  member.active = active;
  return { ...member };
}

export function resetMembers() {
  memberStore._byId.clear();
}
__LENDWELL_REF_EOF__

mkdir -p 'src/members'
cat > 'src/members/membership.js' <<'__LENDWELL_REF_EOF__'
// Membership tiers. fineShare is the part of a late fine the member pays, rounded down in the
// member's favour (seniors: board decision, April 2019).

const TIERS = {
  adult: { loanLimit: 10, fineShare: [1, 1] },
  child: { loanLimit: 5, fineShare: [1, 2] },
  senior: { loanLimit: 10, fineShare: [2, 3] },
  staff: { loanLimit: 25, fineShare: [0, 1] },
};

export const TIER_NAMES = Object.keys(TIERS);

export function isTier(tier) {
  return Object.hasOwn(TIERS, tier);
}

export function loanLimitFor(tier) {
  return TIERS[tier]?.loanLimit ?? 0;
}

export function applyFineShare(tier, totalCents) {
  const [numerator, denominator] = TIERS[tier]?.fineShare ?? [1, 1];
  return Math.floor((totalCents * numerator) / denominator);
}
__LENDWELL_REF_EOF__

mkdir -p 'src/notifications'
cat > 'src/notifications/notifier.js' <<'__LENDWELL_REF_EOF__'
import { renderNotice } from './templates.js';
import { sendEmail } from './channels/email.js';

const outbox = [];

// Kept for callers of the public API; notices no longer need starting.
export function startNotifications() {}

export function notify(kind, member, data) {
  const message = renderNotice(kind, { memberName: member.name, ...data });
  if (!message) throw new Error(`no template for notice kind ${kind}`);
  const sent = sendEmail(member.email, message);
  outbox.push({ kind, memberId: member.id, ...sent });
  return sent;
}

export function sentMessages() {
  return outbox.map((message) => ({ ...message }));
}

export function resetNotifications() {
  outbox.length = 0;
}
__LENDWELL_REF_EOF__

mkdir -p 'src/notifications'
cat > 'src/notifications/overdue-notices.js' <<'__LENDWELL_REF_EOF__'
import { listLoans } from '../circulation/loans.js';
import { getMember } from '../members/member-store.js';
import { getItem } from '../catalog/catalog-store.js';
import { daysBetween, formatNoticeDate } from '../shared/dates.js';
import { requireDate } from '../shared/validate.js';
import { notify } from './notifier.js';

// Run nightly: a member hears about an overdue item on its first day overdue, then weekly.
export function sendOverdueNotices(on) {
  requireDate(on, 'on');
  const sent = [];
  for (const loan of listLoans({ open: true })) {
    const daysOverdue = daysBetween(loan.dueOn, on);
    if (daysOverdue < 1 || (daysOverdue !== 1 && daysOverdue % 7 !== 0)) continue;
    const member = getMember(loan.memberId);
    const item = getItem(loan.itemId);
    notify('loan.overdue', member, { title: item.title, dueOn: formatNoticeDate(loan.dueOn), daysOverdue });
    sent.push({ loanId: loan.id, memberId: member.id, daysOverdue });
  }
  return sent;
}
__LENDWELL_REF_EOF__

mkdir -p 'src/notifications'
cat > 'src/notifications/preview.js' <<'__LENDWELL_REF_EOF__'
import { sampleNotice } from './templates.js';

export function previewNotice(kind, memberName = 'Sample Member') {
  return sampleNotice(kind, memberName);
}
__LENDWELL_REF_EOF__

mkdir -p 'src/notifications'
cat > 'src/notifications/templates.js' <<'__LENDWELL_REF_EOF__'
// Notice templates, one per kind, each with the sample values the operator preview uses.
// Bodies are plain text: the mail relay strips HTML and the same text is printed as a letter.
// The hold-ready wording is parsed back by reports/notice-digest.js.

const TEMPLATES = {
  'hold.ready': {
    sample: { title: 'The Salt Road', branchName: 'Central Library', until: '2026-03-14' },
    render: ({ memberName, title, branchName, until }) => ({
      subject: 'Your hold is ready',
      body: `Hello ${memberName}, "${title}" is ready for pickup at ${branchName} until ${until}.`,
    }),
  },
  'hold.expired': {
    sample: { title: 'The Salt Road' },
    render: ({ memberName, title }) => ({
      subject: 'Your hold has expired',
      body: `Hello ${memberName}, your hold on "${title}" was not collected in time and has been released.`,
    }),
  },
  'loan.overdue': {
    sample: { title: 'The Salt Road', dueOn: 'Saturday 7 March 2026', daysOverdue: 3 },
    render: ({ memberName, title, dueOn, daysOverdue }) => ({
      subject: `Overdue: ${title}`,
      body:
        `Hello ${memberName}, "${title}" was due back on ${dueOn} and is now ` +
        `${daysOverdue} day${daysOverdue === 1 ? '' : 's'} overdue.`,
    }),
  },
};

export function renderNotice(kind, data) {
  const template = TEMPLATES[kind];
  return template ? template.render(data) : null;
}

export function sampleNotice(kind, memberName) {
  const template = TEMPLATES[kind];
  return template ? template.render({ memberName, ...template.sample }) : null;
}
__LENDWELL_REF_EOF__

mkdir -p 'src/reports'
cat > 'src/reports/circulation-report.js' <<'__LENDWELL_REF_EOF__'
import { listLoans } from '../circulation/loans.js';
import { ITEM_TYPES } from '../catalog/item-types.js';
import { listItems } from '../catalog/catalog-store.js';
import { BRANCHES } from '../shared/branches.js';
import { countBy } from '../shared/collections.js';
import { requireDate } from '../shared/validate.js';


function inRange(date, from, to) {
  return date !== null && date >= from && date <= to;
}

export function circulationReport({ from, to }) {
  requireDate(from, 'from');
  requireDate(to, 'to');
  const typeOf = new Map(listItems().map((item) => [item.id, item.type]));
  const checkouts = {};
  const returns = {};
  for (const loan of listLoans()) {
    const type = typeOf.get(loan.itemId);
    if (inRange(loan.checkedOutOn, from, to)) checkouts[type] = (checkouts[type] ?? 0) + 1;
    if (inRange(loan.returnedOn, from, to)) returns[type] = (returns[type] ?? 0) + 1;
  }
  // One row per type, in catalogue order, even when a type had no activity.
  return ITEM_TYPES.map((type) => ({
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
  const loans = listLoans().filter((loan) => inRange(loan.checkedOutOn, from, to));
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
__LENDWELL_REF_EOF__

mkdir -p 'src/reports'
cat > 'src/reports/daily-summary.js' <<'__LENDWELL_REF_EOF__'
// End-of-day numbers each branch manager signs off: what went out, what came back, what was
// charged and taken at the desk.

import { listLoans } from '../circulation/loans.js';
import { allEntries } from '../fines/ledger.js';
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

  for (const loan of listLoans()) {
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
  for (const entry of allEntries()) {
    if (entry.on !== on) continue;
    if (entry.kind === 'payment') collectedCents -= entry.amountCents;
    else if (entry.kind === 'waiver') waivedCents -= entry.amountCents;
    else chargedCents += entry.amountCents;
  }

  return {
    on,
    branches: Object.entries(perBranch).map(([branch, counts]) => ({ branch, ...counts })),
    charged: formatCents(chargedCents),
    collected: formatCents(collectedCents),
    waived: formatCents(waivedCents),
  };
}
__LENDWELL_REF_EOF__

mkdir -p 'src/reports'
cat > 'src/reports/exports.js' <<'__LENDWELL_REF_EOF__'
// Quarterly loan export for the state library statistics return. One row per loan made in the
// period; no member data leaves the building.

import { listLoans } from '../circulation/loans.js';
import { listItems } from '../catalog/catalog-store.js';
import { requireDate } from '../shared/validate.js';

const COLUMNS = ['loan_id', 'item_type', 'branch', 'checked_out', 'due', 'returned', 'renewals'];

export function loansCsv({ from, to }) {
  requireDate(from, 'from');
  requireDate(to, 'to');
  const items = new Map(listItems().map((item) => [item.id, item]));
  const lines = [COLUMNS.join(',')];
  for (const loan of listLoans()) {
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
__LENDWELL_REF_EOF__

mkdir -p 'src/reports'
cat > 'src/reports/fines-report.js' <<'__LENDWELL_REF_EOF__'
import { balancesByMember } from '../fines/ledger.js';
import { findMember } from '../members/member-store.js';
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
  for (const { memberId, balanceCents } of balancesByMember()) {
    if (balanceCents <= 0) continue;
    const member = findMember(memberId);
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
  const totalCents = rows.reduce((sum, row) => sum + row.balanceCents, 0);
  return {
    members: rows.length,
    totalCents,
    total: formatCents(totalCents),
    averageCents: rows.length === 0 ? 0 : Math.round(totalCents / rows.length),
  };
}
__LENDWELL_REF_EOF__

mkdir -p 'src/reports'
cat > 'src/reports/hold-queue-report.js' <<'__LENDWELL_REF_EOF__'
// Titles with the longest hold queues. Selection uses it to decide which titles get extra copies.

import { listItems } from '../catalog/catalog-store.js';
import { holdQueue } from '../holds/holds.js';
import { daysBetween } from '../shared/dates.js';
import { requireDate } from '../shared/validate.js';

export function holdQueueReport(on, { minimum = 1 } = {}) {
  requireDate(on, 'on');
  const rows = [];
  for (const item of listItems()) {
    const queue = holdQueue(item.id);
    const waiting = queue.length;
    if (waiting < minimum) continue;
    const oldest = queue[0];
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
__LENDWELL_REF_EOF__

mkdir -p 'src/reports'
cat > 'src/reports/notice-digest.js' <<'__LENDWELL_REF_EOF__'
// Morning digest for branch staff: the hold-ready notices that went out, grouped by branch, so
// they can check the hold shelf against what members were told.

import { sentMessages } from '../notifications/notifier.js';

const READY = /"(.+)" is ready for pickup at (.+) until (\d{4}-\d{2}-\d{2})\.$/;

export function holdPickupDigest() {
  const byBranch = {};
  for (const message of sentMessages()) {
    if (message.kind !== 'hold.ready') continue;
    const match = READY.exec(message.body);
    if (!match) continue;
    const [, title, branch, until] = match;
    if (!byBranch[branch]) byBranch[branch] = [];
    byBranch[branch].push({ title, until, memberId: message.memberId });
  }
  return byBranch;
}
__LENDWELL_REF_EOF__

mkdir -p 'src/reports'
cat > 'src/reports/overdue-report.js' <<'__LENDWELL_REF_EOF__'
import { listLoans } from '../circulation/loans.js';
import { getMember } from '../members/member-store.js';
import { daysBetween } from '../shared/dates.js';
import { getItem } from '../catalog/catalog-store.js';
import { lateFineCents } from '../fines/fines.js';
import { formatCents } from '../shared/money.js';
import { requireDate } from '../shared/validate.js';

// The list the desk works through when phoning members: longest overdue first.
export function overdueReport(on) {
  requireDate(on, 'on');
  const rows = [];
  for (const loan of listLoans({ open: true })) {
    const daysOverdue = daysBetween(loan.dueOn, on);
    if (daysOverdue <= 0) continue;
    const member = getMember(loan.memberId);
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
__LENDWELL_REF_EOF__

mkdir -p 'src/shared'
cat > 'src/shared/branches.js' <<'__LENDWELL_REF_EOF__'
// The county system's branches. Ids are what we store on items and members; names are what
// members see on notices and receipts. Weekdays follow Date#getUTCDay (0 is Sunday).

export const BRANCHES = {
  main: { name: 'Central Library', address: '1 Market Square', openWeekdays: [1, 2, 3, 4, 5, 6], holdShelfDays: 7 },
  // Harbor opens four days a week, so holds wait longer there.
  harbor: { name: 'Harbor Branch', address: '14 Quay Road', openWeekdays: [3, 4, 5, 6], holdShelfDays: 10 },
  hill: { name: 'Hill Street Branch', address: '200 Hill Street', openWeekdays: [1, 2, 3, 4, 5], holdShelfDays: 7 },
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

export function holdShelfDaysFor(id) {
  return BRANCHES[id]?.holdShelfDays ?? 7;
}
__LENDWELL_REF_EOF__

mkdir -p 'src/shared'
cat > 'src/shared/calendar.js' <<'__LENDWELL_REF_EOF__'
import { LendError } from './errors.js';
import { isIsoDate } from './dates.js';

let closed = [];

export function setClosedDates(dates) {
  if (!Array.isArray(dates)) throw new LendError('BAD_REQUEST', 'closed dates must be a list');
  for (const date of dates) {
    if (!isIsoDate(date)) throw new LendError('BAD_DATE', `not a calendar date: ${date}`);
  }
  closed = [...new Set(dates)].sort();
  return closed.slice();
}

export function listClosedDates() {
  return closed.slice();
}

export function isClosed(date) {
  return closed.includes(date);
}
__LENDWELL_REF_EOF__

mkdir -p 'src/shared'
cat > 'src/shared/dates.js' <<'__LENDWELL_REF_EOF__'
// Calendar dates as 'YYYY-MM-DD' strings, computed in UTC.

const MS_PER_DAY = 86400000;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const WEEKDAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

export function isIsoDate(value) {
  if (typeof value !== 'string' || !ISO_DATE.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

const toTime = (date) => Date.parse(`${date}T00:00:00Z`);

export function addDays(date, days) {
  return new Date(toTime(date) + days * MS_PER_DAY).toISOString().slice(0, 10);
}

export function daysBetween(from, to) {
  return Math.round((toTime(to) - toTime(from)) / MS_PER_DAY);
}

export function formatNoticeDate(date) {
  const d = new Date(toTime(date));
  return `${WEEKDAY_NAMES[d.getUTCDay()]} ${d.getUTCDate()} ${MONTH_NAMES[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}
__LENDWELL_REF_EOF__

mkdir -p 'src/shared'
cat > 'src/shared/errors.js' <<'__LENDWELL_REF_EOF__'
export class LendError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'LendError';
    this.code = code;
  }
}
__LENDWELL_REF_EOF__

mkdir -p 'src/shared'
cat > 'src/shared/money.js' <<'__LENDWELL_REF_EOF__'
import { CURRENCY } from '../config.js';

const SYMBOLS = { USD: '$', EUR: '€', GBP: '£', CAD: 'CA$' };

export function formatCents(cents) {
  if (!Number.isInteger(cents)) throw new TypeError(`cents must be an integer, got ${cents}`);
  const sign = cents < 0 ? '-' : '';
  const abs = Math.abs(cents);
  const whole = String(Math.floor(abs / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const fraction = String(abs % 100).padStart(2, '0');
  const symbol = SYMBOLS[CURRENCY] ?? `${CURRENCY} `;
  return `${sign}${symbol}${whole}.${fraction}`;
}
__LENDWELL_REF_EOF__

mkdir -p 'src/shared'
cat > 'src/shared/validate.js' <<'__LENDWELL_REF_EOF__'
import { LendError } from './errors.js';
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
__LENDWELL_REF_EOF__

mkdir -p 'tests'
cat > 'tests/circulation.test.js' <<'__LENDWELL_REF_EOF__'
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
  assert.deepEqual(listLoans().map((l) => [l.itemId, l.dueOn]), [[book.id, '2026-03-22']]);
});
__LENDWELL_REF_EOF__

mkdir -p 'tests'
cat > 'tests/dates.test.js' <<'__LENDWELL_REF_EOF__'
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
  assert.equal(dueDateFor('2026-03-01', 21), '2026-03-22');
});
__LENDWELL_REF_EOF__

mkdir -p 'tests'
cat > 'tests/fines.test.js' <<'__LENDWELL_REF_EOF__'
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

test('children pay half', () => {
  const ben = registerMember({ name: 'Ben Okafor', tier: 'child' });
  assert.equal(lateReturn(ben, { daysLate: 4 }).fineCents, 50);
});

test('staff pay no fines', () => {
  const dev = registerMember({ name: 'Dev Patel', tier: 'staff' });
  assert.equal(lateReturn(dev, { type: 'dvd', daysLate: 9 }).fineCents, 0);
});

test('a fine is capped at the replacement cost of the item', () => {
  const ada = registerMember({ name: 'Ada Okafor' });
  const result = lateReturn(ada, { daysLate: 100, replacementCostCents: 1200 });
  assert.equal(result.fineCents, 1200);
});

test('formats amounts for people', () => {
  assert.equal(formatCents(1250), '$12.50');
  assert.equal(formatCents(-123456), '-$1,234.56');
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
__LENDWELL_REF_EOF__

mkdir -p 'tests'
cat > 'tests/holds.test.js' <<'__LENDWELL_REF_EOF__'
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
  cancelHold(hold.id, '2026-03-03');
  assert.equal(listHolds({ itemId: book.id, status: 'waiting' }).length, 0);
  returnItem(book.id, '2026-03-10');
  assert.equal(getItem(book.id).status, 'available');
});
__LENDWELL_REF_EOF__

mkdir -p 'tests'
cat > 'tests/members.test.js' <<'__LENDWELL_REF_EOF__'
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
  registerMember({ name: 'Ben Okafor' });
  assert.deepEqual(listMembers().map((m) => m.name), ['Ada Okafor', 'Ben Okafor']);
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
__LENDWELL_REF_EOF__
