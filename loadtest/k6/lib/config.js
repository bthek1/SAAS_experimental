// Shared config for the k6 scenarios (#9).
//
// ⚠️ Load tests only ever target our own deploy on a private network. Pointed at
// someone else's site, a load test is a denial-of-service attack. BASE_URL is
// checked here, before any request, and anything but a private address or a
// private name aborts the run. backend/tests/test_k6_targets.py also scans
// these files for public hosts.

// The local stack's gateway (infra/docker/docker-compose.loadtest.yml).
const DEFAULT_BASE_URL = 'http://api.loadtest.internal:8000';

export function isPrivateHost(host) {
  if (host === 'localhost' || /\.(lan|internal|local|localhost)$/.test(host)) return true;
  const m = host.match(/^(\d+)\.(\d+)\.(\d+)\.(\d+)$/);
  if (!m) return false;
  const [a, b] = [Number(m[1]), Number(m[2])];
  return a === 10 || a === 127 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
}

export function baseUrl() {
  const url = __ENV.BASE_URL || DEFAULT_BASE_URL;
  const match = url.match(/^http:\/\/([^/:]+)(:\d+)?\/?$/);
  if (!match || !isPrivateHost(match[1])) {
    throw new Error(`BASE_URL=${url} is not a private http:// address; refusing to load-test it`);
  }
  return url.replace(/\/$/, '');
}

export const BASE_URL = baseUrl();

// Owners created by `manage.py seed_loadtest` (loadtest-<n>@example.com).
// Each VU logs in as one of them, round robin.
export const OWNERS = Number(__ENV.OWNERS || 5);
export const PASSWORD = __ENV.LOADTEST_OWNER_PASSWORD;
if (!PASSWORD) throw new Error('LOADTEST_OWNER_PASSWORD is not set (the seed_loadtest password)');

export const thresholdsFor = (p95ms) => ({
  // Real failures: anything but the status each request expects.
  http_req_failed: ['rate<0.01'],
  http_req_duration: [`p(95)<${p95ms}`],
  checks: ['rate>0.99'],
});
