// The API calls the scenarios make (#9). Every request carries a `name` tag (an
// endpoint group), so Prometheus gets one series per kind of request rather
// than one per UUID in a URL.

import http from 'k6/http';
import { check } from 'k6';
import { BASE_URL, OWNERS, PASSWORD } from './config.js';

const JSON_HEADERS = { 'Content-Type': 'application/json' };
// Access tokens live 60 minutes (SIMPLE_JWT); log in again well before that.
const SESSION_MAX_AGE_MS = 45 * 60 * 1000;
const DASHBOARD_DAYS = [7, 30, 90];
const SEVERITIES = ['Minimal', 'Mild', 'Moderate', 'Severe'];

const pick = (list) => list[Math.floor(Math.random() * list.length)];

function call(method, path, { name, body = null, token = null, expect = 200, keep = false }) {
  const headers = body === null ? {} : { ...JSON_HEADERS };
  if (token) headers.Authorization = `Bearer ${token}`;
  const params = { headers, tags: { name }, redirects: 0 };
  // Scenarios discard bodies; keep the ones this code reads.
  if (keep) params.responseType = 'text';
  const res = http.request(method, `${BASE_URL}${path}`, body === null ? null : JSON.stringify(body), params);
  check(res, { [`${name} ${expect}`]: (r) => r.status === expect });
  return res;
}

// ── Owner session (one per VU: module state is per VU in k6) ────────────────

let session = null;

function login() {
  const email = `loadtest-${(__VU - 1) % OWNERS}@example.com`;
  const res = call('POST', '/api/token/', { name: 'token', body: { email, password: PASSWORD }, keep: true });
  if (res.status !== 200) {
    throw new Error(`login as ${email} answered ${res.status}; run seed_loadtest with OWNERS >= ${OWNERS}`);
  }
  const token = res.json('access');
  // Lists are paginated (#10): the largest page is enough to pick ids from.
  // A bare array is still read, so runs against a deploy from before #10 work.
  const list = (path, name) => {
    const body = call('GET', `${path}?page_size=100`, { name, token, keep: true }).json();
    return Array.isArray(body) ? body : body.results;
  };
  const types = list('/api/questionnaire-types/', 'questionnaire-type-list');
  const rows = list('/api/questionnaires/', 'questionnaire-list');
  const batteryTypes = list('/api/battery-types/', 'battery-type-list');
  if (!types.length || !rows.length || !batteryTypes.length) {
    throw new Error(`${email} has no data; run seed_loadtest first`);
  }
  return {
    token,
    at: Date.now(),
    typeIds: types.map((t) => t.id),
    batteryTypeIds: batteryTypes.map((t) => t.id),
    questionnaireIds: rows.map((q) => q.id),
    submittedIds: rows.filter((q) => q.submittedAt).map((q) => q.id),
  };
}

export function owner() {
  if (!session || Date.now() - session.at > SESSION_MAX_AGE_MS) session = login();
  return session;
}

// ── Requests, by endpoint group ─────────────────────────────────────────────

const READS = [
  (s) => call('GET', '/api/questionnaires/', { name: 'questionnaire-list', token: s.token }),
  (s) => call('GET', `/api/questionnaires/${pick(s.questionnaireIds)}/`, { name: 'questionnaire-detail', token: s.token }),
  (s) => call('GET', '/api/questionnaire-types/', { name: 'questionnaire-type-list', token: s.token }),
  (s) => call('GET', '/api/batteries/', { name: 'battery-list', token: s.token }),
  (s) => call('GET', `/api/dashboard/?days=${pick(DASHBOARD_DAYS)}`, { name: 'dashboard', token: s.token }),
  (s) =>
    call('GET', `/api/dashboard/scores/?questionnaireType=${pick(s.typeIds)}&days=${pick(DASHBOARD_DAYS)}`, {
      name: 'dashboard-scores',
      token: s.token,
    }),
];

// One owner read, chosen at random.
export function ownerRead(s) {
  pick(READS)(s);
}

// Every owner read once (smoke).
export function allOwnerReads(s) {
  for (const read of READS) read(s);
}

function scoredAnswers() {
  const a = 1 + Math.floor(Math.random() * 5);
  const b = 1 + Math.floor(Math.random() * 5);
  const total = a + b;
  return {
    answers: { a, b },
    metrics: { total, severity: SEVERITIES[Math.min(Math.floor((total - 2) / 2), 3)], flag: a > 4 },
  };
}

// An owner sends a questionnaire; the respondent opens the link and submits it.
// Each share token is fresh, so a 409 (already submitted) is a real failure.
export function respondent(s) {
  const created = call('POST', '/api/questionnaires/', {
    name: 'questionnaire-create',
    token: s.token,
    body: { questionnaireTypeId: pick(s.typeIds), name: `k6 ${__VU}-${__ITER}` },
    expect: 201,
    keep: true,
  });
  if (created.status !== 201) return;
  const shareToken = created.json('shareToken');
  call('GET', `/api/questionnaires/by-token/${shareToken}/`, { name: 'questionnaire-by-token' });
  call('PATCH', `/api/questionnaires/by-token/${shareToken}/submit/`, {
    name: 'questionnaire-submit',
    body: scoredAnswers(),
  });
}

// An owner sends a battery (creates one questionnaire per slot).
export function ownerWrite(s) {
  call('POST', '/api/batteries/', {
    name: 'battery-create',
    token: s.token,
    body: { batteryTypeId: pick(s.batteryTypeIds), name: `k6 ${__VU}-${__ITER}` },
    expect: 201,
  });
}

export function health() {
  call('GET', '/api/health/', { name: 'health' });
}

export function pdf(s) {
  call('GET', `/api/questionnaires/${pick(s.submittedIds)}/pdf/`, { name: 'questionnaire-pdf', token: s.token });
}

// The traffic mix for load, stress and soak. One iteration is one action:
//   50 % owner read (1 request), 30 % respondent (3 requests),
//   15 % owner write (1 request), 5 % health (1 request).
// So 1 iteration/s is about 1.6 requests/s. PDF export is not in the mix (pdf.js).
export function mixed(s) {
  const r = Math.random();
  if (r < 0.5) ownerRead(s);
  else if (r < 0.8) respondent(s);
  else if (r < 0.95) ownerWrite(s);
  else health();
}

// Mostly reads, closer to people using the app than `mixed`, which is 47 % writes.
// The cache comparison needs both (#11).
export function readMostly(s) {
  const r = Math.random();
  if (r < 0.9) ownerRead(s);
  else if (r < 0.95) respondent(s);
  else if (r < 0.98) ownerWrite(s);
  else health();
}

const MIXES = { mixed, read: readMostly };

// The mix for load, stress and soak: MIX=mixed (default) or MIX=read.
const MIX = __ENV.MIX || 'mixed';
if (!MIXES[MIX]) throw new Error(`unknown MIX=${MIX}: use ${Object.keys(MIXES).join(' or ')}`);
export const traffic = MIXES[MIX];
