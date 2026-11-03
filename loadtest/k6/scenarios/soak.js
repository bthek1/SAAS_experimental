// soak: a moderate, steady rate of mixed traffic for a long time. Watch for
// drift: latency creeping up, memory, Postgres connections.
//   RATE (iterations/s, default 5), DURATION (default 30m), MIX (mixed or read)
import { owner, traffic } from '../lib/api.js';
import { thresholdsFor } from '../lib/config.js';

export const options = {
  discardResponseBodies: true,
  scenarios: {
    soak: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 5),
      timeUnit: '1s',
      duration: __ENV.DURATION || '30m',
      preAllocatedVUs: 20,
      maxVUs: 100,
    },
  },
  thresholds: thresholdsFor(500),
};

export default function () {
  traffic(owner());
}
