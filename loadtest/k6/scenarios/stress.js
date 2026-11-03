// stress: keep raising the rate of mixed traffic until p95 latency or errors
// cross the line, then stop. The rate it reached is the ceiling.
//   MAX_RATE (iterations/s, default 200), STEP (default 5), STEP_TIME (default 1m),
//   MIX (mixed or read, default mixed)
import { owner, traffic } from '../lib/api.js';

const MAX = Number(__ENV.MAX_RATE || 200);
const STEP = Number(__ENV.STEP || 5);
const STEP_TIME = __ENV.STEP_TIME || '1m';

const stages = [];
for (let rate = STEP; rate <= MAX; rate += STEP) stages.push({ target: rate, duration: STEP_TIME });

export const options = {
  discardResponseBodies: true,
  scenarios: {
    stress: {
      executor: 'ramping-arrival-rate',
      startRate: STEP,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 300,
      stages,
    },
  },
  thresholds: {
    // Aborting is the point: k6 stops at the first sustained breach, and the
    // stage it reached is the result. delayAbortEval lets a step settle.
    http_req_duration: [{ threshold: 'p(95)<1000', abortOnFail: true, delayAbortEval: '30s' }],
    http_req_failed: [{ threshold: 'rate<0.01', abortOnFail: true, delayAbortEval: '30s' }],
    // VUs exhausted means k6 itself cannot keep the rate: also a ceiling.
    dropped_iterations: [{ threshold: 'count<1000', abortOnFail: true }],
  },
};

export default function () {
  traffic(owner());
}
