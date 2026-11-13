# Load-test baseline: 2026-11-11, `catalog` alone, Django against FastAPI

Plan: #39. Scenario: `loadtest/k6/scenarios/catalog.js` (`just k6 catalog`), which loads only `catalog`'s
endpoints. Django ran from `02e485a` (the last commit with it), extracted with `git archive` and deployed by
that commit's own Ansible (`-e catalog_impl=django`). FastAPI ran from `42d0f4b` plus the working tree. Between
the two, `instances`, `common`, the contracts and the tuning are identical.

**Summary.** The mixed traffic of [2026-11-11-catalog-fastapi.md](2026-11-11-catalog-fastapi.md) left `catalog`
near idle, so it showed no difference. On `catalog`'s own traffic, the first FastAPI runs **reached less than half
Django's knee**, from two bugs that the mixed traffic never reached. With both fixed, **FastAPI reaches ~532 to ~594
req/s against Django's ~409 to ~431**. At the same 240 req/s it has **p95 16.5 ms against 27.6 ms, at 25 % CPU
against 41 %**. Logins, which are mostly the password hash, are the same on both (~17 per second).

## Traffic

`CATALOG_MIX=crud`, ~1.2 requests per iteration:

| Share | Requests |
|---:|---|
| 35 % | type list |
| 15 % | type detail |
| 15 % | battery-type list |
| 10 % | `/api/accounts/me/` |
| 10 % | token refresh |
| 10 % | type create, update and delete (3 requests; each write sends an event to `instances`, the delete also retires the type there) |
| 5 % | health |

`CATALOG_MIX=login`: one login per iteration. Stress: `MAX_RATE=1500 START_RATE=100 STEP=50 STEP_TIME=1m` (CRUD)
and `MAX_RATE=30 START_RATE=1 STEP=1 STEP_TIME=1m` (login). Fixed rate: `RATE=200 HOLD=5m` (CRUD, ~240 req/s, ~60 % of
Django's knee) and `RATE=12 HOLD=5m` (login, ~70 %). Every run started from `app_reset_db=true`.

## What the first FastAPI runs found

1. **The signing key was parsed on every token.** `token-refresh` averaged 65 ms on FastAPI against 2.8 ms on
   Django. PyJWT, given the PEM string, parses and validates the RSA key on every signature: 25 ms of CPU each,
   against 0.19 ms to sign with a loaded key. A refresh signs twice, and so does a login. Fix: `auth._signing_key`
   parses each PEM once (`test_the_signing_key_is_parsed_once`).
2. **A new HTTP client for every call to `instances`.** `httpx.request()` builds a client and an SSL context per
   call: 3.6 ms of CPU against 0.42 ms with a shared client, measured locally. It also leaked memory: `catalog`'s
   workers grew from ~135 to ~275 MiB each in 5 minutes of this traffic, and the outbox relay grew too. Every type
   write sends an event, and every delete retires the type. Fix: `peers.http_client()`, one per process
   (`test_peer_calls_share_one_http_client`). `instances` has the same pattern in `common/peers.py`, left for a
   separate change.

## Stress, CRUD

| Run | Code | Last clean minute | Slowest group p95 | `catalog` CPU | Failed |
|---|---|---:|---:|---:|---:|
| `catalog-20261111T132315Z` | Django | 6 at **~431 req/s** | 97 ms | 79 % | 0 |
| `catalog-20261111T133042Z` | Django | 6 at **~409 req/s** | 105 ms | 80 % | 0 |
| `catalog-20261111T135725Z` | FastAPI, no fix | 2 at ~183 req/s | 267 ms | 76 % | 0 |
| `catalog-20261111T140027Z` | FastAPI, no fix | 2 at ~176 req/s | 293 ms | 73 % | 0 |
| `catalog-20261111T141819Z` | FastAPI, key fix | 5 at ~375 req/s | 129 ms | 75 % | 0 |
| `catalog-20261111T142437Z` | FastAPI, key fix | 5 at ~350 req/s | 93 ms | 63 % | 0 |
| `catalog-20261111T152538Z` | FastAPI, both fixes | 8 at **~532 req/s** | 45 ms | 61 % | 0 |
| `catalog-20261111T153436Z` | FastAPI, both fixes | 9 at **~594 req/s** | 84 ms | 74 % | 0 |

- **CPU at the same rate:** at ~410 req/s, `catalog` used 79 to 80 % on Django and 44 to 46 % on FastAPI with both fixes.
- **What ended each run, on both:** latency rose, k6 jumped to its 300 VUs, and every new VU logged in at once
  (`token` p95 3.0 to 3.6 s). The knees are where k6's login burst tips the service over, so they understate what
  `catalog` serves to users already logged in. That affects both implementations alike.
- saas-gateway stayed at 3 to 6 % CPU and saas-loadgen at 4 to 7 %, so neither limited the runs.

## Stress, login

| Run | Code | Last clean minute | Slowest p95 | `catalog` CPU |
|---|---|---:|---:|---:|
| `catalog-20261111T133726Z` | Django | 17 at **17.0/s** | 229 ms | 93 % |
| `catalog-20261111T140322Z` | FastAPI, no fix | 11 at 11.1/s | 248 ms | 90 % |
| `catalog-20261111T143044Z` | FastAPI, key fix | 17 at **16.8/s** | 208 ms | 92 % |

Each login is a pbkdf2 hash at 1.2 million iterations, so both are CPU-bound at the same rate once FastAPI stops
re-parsing the key. Logins make no call to `instances`, so the client fix does not apply.

## Fixed rate, back to back

CRUD at ~240 req/s, final code (`catalog-20261111T154447Z` Django, `catalog-20261111T155205Z` FastAPI). Both: 0
failed, 0 dropped, ~82,700 requests.

| | Django | FastAPI |
|---|---:|---:|
| Mean | 7.89 ms | 5.11 ms |
| p95 | 27.61 ms | 16.52 ms |
| Max | 225 ms | 148 ms |
| `catalog` CPU | 41.4 % | 25.4 % |
| saas-db CPU | 7.1 % | 7.9 % |
| `instances` CPU | 10.6 % | 9.0 % |
| `catalog` memory, working set | 570 MiB | 586 MiB |

| Group | Django mean / p95 | FastAPI mean / p95 |
|---|---:|---:|
| questionnaire-type-list | 3.35 / 8.52 ms | 2.22 / 4.07 ms |
| questionnaire-type-detail | 3.12 / 7.35 ms | 2.15 / 3.71 ms |
| battery-type-list | 3.98 / 10.06 ms | 2.61 / 4.95 ms |
| me | 2.60 / 6.50 ms | 1.51 / 2.73 ms |
| token-refresh | 2.99 / 7.21 ms | 1.87 / 3.18 ms |
| questionnaire-type-create | 20.03 / 32.88 ms | 13.53 / 19.20 ms |
| questionnaire-type-update | 20.81 / 34.46 ms | 13.55 / 19.85 ms |
| questionnaire-type-delete | 27.17 / 43.74 ms | 15.39 / 22.25 ms |
| health | 1.09 / 3.20 ms | 0.54 / 1.14 ms |

`catalog`'s anonymous memory over the 5 minutes: Django 283 → 418 MiB, FastAPI 414 → 443 MiB, both levelling off.
Before the client fix, FastAPI's rose from 416 to 836 MiB in 4 minutes and kept rising.

An earlier pair with the key fix only (`catalog-20261111T145026Z`, `catalog-20261111T145746Z`) had FastAPI ahead
by less: mean 7.83 against 9.09 ms, `catalog` CPU 40 % against 46 %.

Login at 12/s (`catalog-20261111T150441Z` Django, `catalog-20261111T151200Z` FastAPI with the key fix): `token`
p95 151.9 against 146.5 ms, mean 121.4 against 118.4 ms, `catalog` CPU 63 against 65 %. The same.

## How far to trust it

- **Two stress runs per version.** They agree within ~60 req/s, but the knee comes from k6's login burst on both.
- **Django ran from an older commit.** Everything but `catalog` is identical to the FastAPI deploy, and its own
  Ansible deployed it, so it is the Django `catalog` as it last shipped.
- **Writes depend on `instances`.** Their latency includes `instances` handling the event or the retire, the
  same on both.
- **Host load was not recorded.**

## Two smaller fixes (#41, 2026-11-13)

Endpoints build their JSON themselves (`catalog/responses.py`) instead of returning dicts for FastAPI to walk
through `jsonable_encoder`, and a cache hit goes out as Redis's bytes. `pool_pre_ping` is replaced by a ping
only for a connection idle more than 5 s (`db.PING_AFTER_IDLE`).

A first single run against the #39 reference (`catalog-20261113T040659Z`) was ~10 % slower in every group,
`health` included, which neither change touches: the two days between them moved the numbers more than the
code. So the comparison is four runs back to back, each from a fresh database: HEAD (`4ec41e0`), the change,
the change, HEAD. `CATALOG_MIX=crud RATE=200 HOLD=5m`, 0 failed and 0 dropped in all four.

| | Before (HEAD) | After |
|---|---:|---:|
| Median | 2.28, 2.29 ms | 2.05, 2.05 ms |
| Mean | 5.58, 5.29 ms | 4.73, 5.41 ms |
| p95 | 17.86, 17.16 ms | 15.18, 17.59 ms |
| `catalog` CPU | 26.0, 25.2 % | 24.0, 24.8 % |
| saas-db transactions per second | 902, 867 | 483, 508 |
| Test ids | `catalog-20261113T041514Z`, `catalog-20261113T043624Z` | `catalog-20261113T042226Z`, `catalog-20261113T042914Z` |

Median per read group, mean of the two runs:

| Group | Before | After |
|---|---:|---:|
| type list | 1.98 ms | 1.72 ms |
| type detail | 1.90 ms | 1.70 ms |
| battery-type list | 2.50 ms | 2.35 ms |
| me | 1.32 ms | 1.17 ms |
| token refresh | 1.67 ms | 1.50 ms |
| health | 0.42 ms | 0.37 ms |

- **Reads gain 0.15 to 0.26 ms each, in both runs.** Writes (11 to 14.5 ms median), the mean and p95 vary more
  from run to run than between the versions.
- **saas-db does ~45 % fewer transactions**: the pings were about 400 a second. Only 32 idle pings in a whole run.
- **The encoding saving depends on page size.** Seeded owners have 3 small types, where it is ~0.06 ms per list.
  On 25 seeded-size types it is ~0.48 ms, and on 25 types with 10-question definitions ~2.5 ms (measured
  locally). Real owners with many or large types gain more than this run shows.

## Still open

- `common/peers.py` builds a client per call too, so `instances`' read-through to `catalog` pays the same cost.
- Log k6's VUs in before the ramp, or pre-allocate them, to see `catalog`'s knee without the login burst.
