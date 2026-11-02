// pdf: PDF export only (WeasyPrint, CPU-heavy). Kept out of the mixed traffic
// so its cost cannot hide everything else.
//   RATE (exports/s, default 1), DURATION (default 2m)
import { owner, pdf } from '../lib/api.js';
import { thresholdsFor } from '../lib/config.js';

export const options = {
  discardResponseBodies: true,
  scenarios: {
    pdf: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 1),
      timeUnit: '1s',
      duration: __ENV.DURATION || '2m',
      preAllocatedVUs: 5,
      maxVUs: 50,
    },
  },
  thresholds: thresholdsFor(3000),
};

export default function () {
  pdf(owner());
}
