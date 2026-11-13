// catalog: only `catalog`'s endpoints, to measure that service alone (#39). The
// other scenarios send most traffic to `instances`, where `catalog` stays near idle.
//   CATALOG_MIX=crud (default): lib/api.js `catalogCrud`, ~1.2 requests per iteration
//   CATALOG_MIX=login: each iteration one login as the next owner (the pbkdf2 path)
//   (Not MIX: lib/api.js refuses any MIX but mixed or read when it loads.)
//   Fixed rate: RATE (iterations/s, default 10), HOLD (default 5m)
//   Stress, when MAX_RATE is set: START_RATE (default STEP), STEP (default 10),
//     STEP_TIME (default 1m), stopping at the first sustained breach, as stress.js does
import { catalogCrud, catalogOwner, loginOnly } from '../lib/api.js';

const MIX = __ENV.CATALOG_MIX || 'crud';
if (!['crud', 'login'].includes(MIX)) throw new Error(`unknown CATALOG_MIX=${MIX}: use crud or login`);

const STRESS = Boolean(__ENV.MAX_RATE);
const STEP = Number(__ENV.STEP || 10);

function stages() {
  if (!STRESS) {
    const rate = Number(__ENV.RATE || 10);
    return [
      { target: rate, duration: '1m' },
      { target: rate, duration: __ENV.HOLD || '5m' },
      { target: 0, duration: '30s' },
    ];
  }
  const out = [];
  const max = Number(__ENV.MAX_RATE);
  for (let rate = Number(__ENV.START_RATE || STEP); rate <= max; rate += STEP) {
    out.push({ target: rate, duration: __ENV.STEP_TIME || '1m' });
  }
  return out;
}

export const options = {
  discardResponseBodies: true,
  scenarios: {
    catalog: {
      executor: 'ramping-arrival-rate',
      startRate: 1,
      timeUnit: '1s',
      preAllocatedVUs: STRESS ? 50 : 20,
      maxVUs: 300,
      stages: stages(),
    },
  },
  thresholds: STRESS
    ? {
        http_req_duration: [{ threshold: 'p(95)<1000', abortOnFail: true, delayAbortEval: '30s' }],
        http_req_failed: [{ threshold: 'rate<0.01', abortOnFail: true, delayAbortEval: '30s' }],
        dropped_iterations: [{ threshold: 'count<1000', abortOnFail: true }],
      }
    : {
        http_req_failed: ['rate<0.005'],
        checks: ['rate>0.995'],
        dropped_iterations: ['count<1'],
      },
};

export default function () {
  if (MIX === 'login') loginOnly();
  else catalogCrud(catalogOwner());
}
