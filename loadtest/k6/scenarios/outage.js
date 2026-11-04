// outage: the respondent flow keeps working while `catalog` is stopped (#13).
// Setup logs in and creates the questionnaires, so it needs both services. Stop catalog once
// the run starts (ssh root@<app> systemctl stop saas-app), start it afterwards, and check the
// outbox drains. Every token is used once, so a 409 or any 5xx fails a check.
//   RATE (flows/s, default 5), DURATION in seconds (default 120)
import http from 'k6/http';
import { check, fail } from 'k6';
import exec from 'k6/execution';
import { BASE_URL, PASSWORD } from '../lib/config.js';

const RATE = Number(__ENV.RATE || 5);
const DURATION = Number(__ENV.DURATION || 120);
const JSON_HEADERS = { 'Content-Type': 'application/json' };

export const options = {
  setupTimeout: '10m',
  scenarios: {
    outage: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: `${DURATION}s`,
      preAllocatedVUs: 20,
      maxVUs: 100,
    },
  },
  thresholds: {
    checks: ['rate==1.0'],
    'http_req_failed{name:outage-submit}': ['rate==0'],
    'http_req_failed{name:outage-open}': ['rate==0'],
  },
};

function post(path, body, token) {
  const headers = { ...JSON_HEADERS };
  if (token) headers.Authorization = `Bearer ${token}`;
  return http.post(`${BASE_URL}${path}`, JSON.stringify(body), { headers, tags: { name: 'outage-setup' } });
}

export function setup() {
  const login = post('/api/token/', { email: 'loadtest-0@example.com', password: PASSWORD });
  if (login.status !== 200) fail(`login answered ${login.status}`);
  const token = login.json('access');
  const types = http.get(`${BASE_URL}/api/questionnaire-types/?page_size=1`, {
    headers: { Authorization: `Bearer ${token}` },
    tags: { name: 'outage-setup' },
  });
  const typeId = types.json('results.0.id');
  const shareTokens = [];
  // Some spare: an arrival-rate executor can start slightly more than rate x duration.
  for (let i = 0; i < RATE * DURATION + 50; i += 1) {
    const created = post('/api/questionnaires/', { questionnaireTypeId: typeId }, token);
    if (created.status !== 201) fail(`create answered ${created.status}`);
    shareTokens.push(created.json('shareToken'));
  }
  return { shareTokens };
}

export default function (data) {
  const shareToken = data.shareTokens[exec.scenario.iterationInTest];
  const url = `${BASE_URL}/api/questionnaires/by-token/${shareToken}/`;
  const opened = http.get(url, { tags: { name: 'outage-open' } });
  check(opened, { 'open 200': (r) => r.status === 200 });
  const submitted = http.patch(`${url}submit/`, JSON.stringify({ answers: { a: 3, b: 4 }, metrics: { total: 7 } }), {
    headers: JSON_HEADERS,
    tags: { name: 'outage-submit' },
  });
  check(submitted, { 'submit 200': (r) => r.status === 200 });
}
