// load: ramp to a target rate of the mixed traffic and hold it (lib/api.js `mixed`).
//   RATE (iterations/s, default 10; about 1.6 requests each), HOLD (default 5m)
// Phase 5 of #9 replaces the thresholds with ones taken from the baseline.
import { mixed, owner } from '../lib/api.js';
import { thresholdsFor } from '../lib/config.js';

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
  thresholds: thresholdsFor(500),
};

export default function () {
  mixed(owner());
}
