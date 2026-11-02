// respondent: only the share-link flow (create, open, submit), at a steady rate.
// Every token is fresh, so any 409 (already submitted) fails a check.
//   RATE (flows/s, default 5; 3 requests each), DURATION (default 2m)
import { owner, respondent } from '../lib/api.js';
import { thresholdsFor } from '../lib/config.js';

export const options = {
  discardResponseBodies: true,
  scenarios: {
    respondent: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 5),
      timeUnit: '1s',
      duration: __ENV.DURATION || '2m',
      preAllocatedVUs: 10,
      maxVUs: 100,
    },
  },
  thresholds: thresholdsFor(500),
};

export default function () {
  respondent(owner());
}
