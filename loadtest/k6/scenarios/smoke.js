// smoke: 1 VU for 1 minute through every endpoint group. Proves the target,
// the seed data and the pipeline to Prometheus work before any real load.
import { sleep } from 'k6';
import { allOwnerReads, health, owner, ownerWrite, pdf, respondent } from '../lib/api.js';
import { thresholdsFor } from '../lib/config.js';

export const options = {
  discardResponseBodies: true,
  scenarios: { smoke: { executor: 'constant-vus', vus: 1, duration: __ENV.DURATION || '1m' } },
  thresholds: thresholdsFor(1000),
};

export default function () {
  const s = owner();
  allOwnerReads(s);
  respondent(s);
  ownerWrite(s);
  pdf(s);
  health();
  sleep(1);
}
