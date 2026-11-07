# Load-test baseline: 2026-11-06, `instances` on Postgres against MongoDB

Plan: #30 (deploy and compare), on #29 (`instances` runs on either engine). Code: `f9f94e9` plus the
uncommitted #29/#30 working tree. Postgres runs and the first MongoDB runs used tree hash `e28a5eab8237`.
The MongoDB runs reported below, and the Postgres re-checks, used `dc494c1d0384`, which adds the two
MongoDB fixes described under "What the first runs found". `runs.log` recorded both hashes.

**Summary.** On the same 2 cores and 1 GB, **MongoDB is slower than Postgres for this workload, and it
gets slower as rows grow.** Every scenario passed with 0 failed requests on both engines, and the
respondent flow kept working with `catalog` down on both. At a fixed 200 iterations/s, p95 was 16.1 ms
on MongoDB against 8.5 ms on Postgres (mixed), and 10.4 against 8.7 ms (read-mostly). The mixed stress
knee was **~322 to ~332 req/s on MongoDB against ~575 to ~614 on Postgres**, and read-mostly ~404 to
~419 against ~495 to ~526. The 1-hour soak at ~350 req/s held on Postgres and was **stopped at minute 18
on MongoDB**, after 5 minutes over 1 % dropped. MongoDB's data takes about half the disk (compressed),
and its indexes take about the same. **Decision: `instances` stays on Postgres.** MongoDB support stays
in the code (#29) and on the deploy (`saas-mongo`), switched off.

## Deploy

Same containers, sizes and seed as [2026-11-06-microservices-full.md](2026-11-06-microservices-full.md)
(20 owners × 200 questionnaires, 2 + 2 cores), plus:

| Container | Size | Runs |
|---|---|---|
| saas-mongo (248) | 2 cores, 1 GB | MongoDB 8.0.34, one-member replica set `rs0`, auth, WiredTiger cache 0.25 GB |

`saas-db` keeps Postgres 16 with `shared_buffers` 256 MB, so both engines have the same cache. The
engine is chosen per reset: `ansible-playbook site.yml --tags app --limit app,instances -e
app_reset_db=true -e instances_db_engine=mongo`, which also seeds that engine. Each scenario ran on
Postgres, then on MongoDB, back to back, each from its own reset.

## What the first runs found

The first MongoDB runs collapsed: `load-20261106T161434Z` had **p95 5.27 s** against 9.36 ms on
Postgres, and dropped 34,253 iterations, with mongod at 98 % CPU. mongod's slow-query log (every
operation over 100 ms, with `docsExamined`) showed two causes, both from how `django-mongodb-backend`
translates the ORM:

1. **Partial unique indexes.** The backend builds every unique index as partial (`{id: {$gte: ""}}`),
   so nulls don't collide, as in SQL. Such an index cannot find `null`. `select_related("battery")` is a
   `$lookup` on `battery.id`, and for every questionnaire with no battery it scanned the whole battery
   collection: 2,822,816 documents examined to return 10 rows. Fix: `core/mongodb/base.py` builds a
   full unique index for a field that can never be null, and migration 0004 rebuilds existing ones.
   p95 went to 160 ms (`load-20261106T203244Z`).
2. **Joins before the limit, and no incremental sort.** The backend puts each `$lookup` before
   `$sort` and `$limit`, so a page of 25 joined all ~3,000 of the owner's rows. And the `-id`
   tiebreaker added for MongoDB's millisecond timestamps (#29) made it sort all of them, since the
   index ended at `created_at`. Fix: `joined()` in `apps/questionnaires/db.py` (a join on Postgres,
   a prefetch on MongoDB), and migration 0005 adds `-id` to the list indexes. p95 went to 16.1 ms
   (`load-20261106T204209Z`).

Fix 2 also changes Postgres's indexes, so Postgres was re-run: no measurable change (below).

## Fixed rate, 5 minutes

`RATE=200 HOLD=5m`, 0 failed requests in all. Database CPU is the container's share of its 2 cores,
minute 5.

| | Postgres mixed | MongoDB mixed | Postgres read | MongoDB read |
|---|---:|---:|---:|---:|
| Run | `load-20261106T204946Z` | `load-20261106T204209Z` | `load-20261106T205637Z` | `load-20261106T210353Z` |
| Requests | 110,445 | 110,386 | 75,900 | 76,128 |
| Mean | 3.86 ms | 6.68 ms | 4.06 ms | 4.85 ms |
| p95, all requests | 8.54 ms | 16.12 ms | 8.74 ms | 10.44 ms |
| Max | 115 ms | 283 ms | 127 ms | 165 ms |
| Dropped iterations | 0 | 1 | 0 | 0 |
| Slowest group p95, minute 1 → 5 | 11 → 17 ms | 37 → 130 ms | 12 → 12 ms | 18 → 28 ms |
| Database CPU, minute 1 → 5 | 5 → 9 % | 16 → 28 % | 5 → 6 % | 7 → 12 % |
| `instances` CPU, minute 5 | 37 % | 43 % | 29 % | 30 % |

The MongoDB mixed run ended with exit 99 on its 1 dropped iteration. MongoDB's database CPU, and its
slowest group, **rise every minute at a constant rate**: the remaining costs grow with rows. Postgres's
earlier runs before fix 2 (`load-20261106T160721Z`, `load-20261106T162148Z`) had p95 9.36 and 8.24 ms.

## Stress

`STEP=10 STEP_TIME=1m MAX_RATE=500`, mixed from `START_RATE=150`, read from 200. The knee is the last
minute with no dropped iterations and the slowest group's p95 under 150 ms.

| | Run | Knee req/s | Mean | Slowest group p95 | `instances` CPU | Database CPU |
|---|---|---:|---:|---:|---:|---:|
| Postgres mixed | `stress-20261106T170912Z` | ~579 | 19.3 ms | 123 ms | 77 % | 25 % |
| Postgres mixed | `stress-20261106T173708Z` | ~614 | 15.2 ms | 101 ms | 79 % | 25 % |
| Postgres mixed, after fix 2 | `stress-20261106T212630Z` | ~575 | 11.9 ms | 90 ms | 73 % | 22 % |
| MongoDB mixed | `stress-20261106T215041Z` | ~332 | 9.3 ms | 147 ms | 44 % | 30 % |
| MongoDB mixed | `stress-20261106T220425Z` | ~322 | 8.5 ms | 127 ms | 43 % | 27 % |
| Postgres read | `stress-20261106T180649Z` | ~526 | 19.5 ms | 95 ms | 85 % | 15 % |
| Postgres read | `stress-20261106T184413Z` | ~509 | 16.0 ms | 80 ms | 82 % | 15 % |
| Postgres read, after fix 2 | `stress-20261106T221832Z` | ~495 | 12.4 ms | 62 ms | 77 % | 14 % |
| MongoDB read | `stress-20261106T224643Z` | ~404 | 20.2 ms | 112 ms | 65 % | 39 % |
| MongoDB read | `stress-20261106T230725Z` | ~419 | 26.1 ms | 145 ms | 67 % | 42 % |

MongoDB's knee came with CPU to spare on both containers. What set it is the slowest group's p95,
which is a dashboard cache miss (below). Postgres was limited, as in #24, by `instances` CPU and k6's
logins on `catalog`. The stress runs' whole-run totals: Postgres mixed 570,197 to 642,892 requests,
MongoDB mixed 255,798 and 259,943, all 0 failed.

## Soak, 1 hour at ~350 req/s

| | Run | Result |
|---|---|---|
| Postgres | `soak-20261106T192016Z` | Held the hour: 1,266,447 requests, 0 failed, 351 dropped (startup). p95 16.6 ms |
| MongoDB | `soak-20261106T232945Z` | **Stopped at minute 18** (AGENTS.md's rule: 5 minutes over 1 % dropped). 391,984 requests, 0 failed |

On MongoDB the slowest group's p95 passed 150 ms at minute 6 and 400 ms at minute 11, while mongod's CPU
climbed from 16 % to 76 % at a constant rate. The first soak, before the two fixes
(`soak-20261106T202141Z`), was stopped at minute 5.

## What is still slow on MongoDB

From mongod's slow-query log during the soak, by total time:

| Query | Slow runs | `docsExamined` first → last | Why |
|---|---:|---|---|
| Dashboard recent submissions (`RESPONDENT`, `questionnaire_type__title`) | 1,407 | 1,763 → 7,305 | Two `$lookup`s on every row in the window before `$sort`/`$limit 10` |
| Dashboard battery status (`battery_rows`) | 943 | 1,989 → 5,355 | `$lookup` of questionnaires into each battery in the window |
| Dashboard scores `points` (`RESPONDENT`) | 583 | 524 → 1,265 | `$lookup` on every row in the window before `$limit 500` |
| Questionnaire list | 15 | 6,112 → 7,637 | The backend's `$addFields` before `$sort` stops the sort from using the index |

All are on Postgres too, as joins or sorts, but its planner limits before it joins and can sort
incrementally from an index. Each could be rewritten for MongoDB (fetch the page, then its related
rows), as `joined()` does for lists. That would need its own engine-specific code, and another
measurement.

## Storage

Freshly seeded (4,000 questionnaires), MongoDB from a newly created database, after `fsync`:

| | Postgres (`pg_total_relation_size`) | MongoDB (`collStats`) |
|---|---:|---:|
| Questionnaires: data | 4.33 MB | 0.81 MB on disk (2.94 MB uncompressed) |
| Questionnaires: indexes | 2.10 MB (8 indexes) | 2.10 MB (9 indexes) |
| All `questionnaires_*` tables | 7.16 MB | 3.63 MB |

MongoDB compresses data (snappy) and Postgres doesn't, below its TOAST threshold. MongoDB's indexes are
no smaller, since UUIDs are stored as 32-character strings, and a UUID primary key adds an `id`
index beside `_id`.

## Correctness

| | Postgres | MongoDB |
|---|---|---|
| Respondent, `RATE=50 DURATION=5m` | `respondent-20261106T163614Z`: p95 4.81 ms, 0 failed of 45,055 | `respondent-20261106T211043Z`: p95 6.83 ms, 0 failed of 45,057 |
| PDF, `RATE=5 DURATION=5m` | `pdf-20261106T164739Z`: p95 104 ms, 0 failed | `pdf-20261106T211607Z`: p95 110 ms, 0 failed |
| Outage, `catalog` stopped ~140 s | `outage-20261106T165904Z`: 0 failed of 2,754 | `outage-20261106T212129Z`: 0 failed of 2,754 |
| Catch-up, `instances` stopped, 3 edits + 1 create | 4 events queued, drained in 10 s, titles right | 4 events queued, drained in 5 s, titles right |

The double-submit guard (a conditional `update()`, #29) gave no 409 in any respondent run, as expected:
each submit uses a fresh questionnaire.

## Caveats

- **`manage.py flush` does not shrink MongoDB.** The reset deletes documents, so after the first run
  each MongoDB run started with files sized by the run before. Free space is reused and is not cached,
  so this should not change latency, but it was not tested. The storage figures above come from a
  newly created database for that reason.
- One run per engine for fixed rate, two for stress, one soak each. The host was shared, as in #24.
- MongoDB support uses `django-mongodb-backend` 6.0.4. The costs above come from how it translates
  queries, and a later version may place `$lookup` differently.
