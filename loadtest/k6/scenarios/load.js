// load: ramp to a target rate of the mixed traffic and hold it (lib/api.js `mixed`).
//   RATE (iterations/s, default 10; about 1.6 requests each), HOLD (default 5m),
//   MIX (mixed or read, default mixed)
//
// The thresholds are a regression check against the cached baseline
// (loadtest/baselines/2026-11-03-redis-cache.md, load-20261103T125112Z): RATE=135
// (~215 req/s) held 10 minutes on the LXC deploy with p95 8.9 ms, max 135 ms, 0
// failed, 0 dropped. p95 drifted 11 -> 29 ms in the worst endpoint group as the run
// grew the data, so the limit is ~2x the baseline p95 rather than a tight margin.
// With the cache off, expect to land near the limit (p95 19 ms on 2026-11-02).
// Reset the data first (`just loadtest-reset`) and compare like with like.
import { owner, traffic } from '../lib/api.js';

const RATE = Number(__ENV.RATE || 10);
const HOLD = __ENV.HOLD || '5m';

export const options = {
  discardResponseBodies: true,
  scenarios: {
    load: {
      executor: 'ramping-arrival-rate',
      startRate: 1,
      timeUnit: '1s',
      preAllocatedVUs: 20,
      maxVUs: 200,
      stages: [
        { target: RATE, duration: '1m' },
        { target: RATE, duration: HOLD },
        { target: 0, duration: '30s' },
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.005'],
    http_req_duration: ['p(95)<20', 'max<1000'],
    checks: ['rate>0.995'],
    // Dropped iterations mean the deploy (or k6) could not keep the rate.
    dropped_iterations: ['count<1'],
  },
};

export default function () {
  traffic(owner());
}
