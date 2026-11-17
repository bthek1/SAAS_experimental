# loadtest/AGENTS.md

k6 load tests and the baselines they produce (plan: #9). Read with the root [`AGENTS.md`](../AGENTS.md). The
server-side metrics rules are in [`backend/AGENTS.md`](../backend/AGENTS.md); the LXC stack is in
[`infra/AGENTS.md`](../infra/AGENTS.md).

⚠️ **k6 only ever targets a private address.** `lib/config.js` refuses any other `BASE_URL` before the first
request, and `backend/tests/test_k6_targets.py` fails on any public host in `loadtest/`. Load-testing a site
you do not own is a denial-of-service attack.

## Commands

```bash
just loadtest-up    # load-test stack: prod backend + Postgres + Prometheus + Grafana
just loadtest-seed --owners 5 --questionnaires-per-owner 200
just k6 <scenario> [KEY=VALUE…]  # smoke load stress soak respondent pdf outage catalog
just k6 <scenario> TARGET=lxc    # run from saas-loadgen through saas-gateway
just k6-report <testid>          # tables for a baseline
just loadtest-reset              # before every measured run
just loadtest-down  # keeps its volumes
```

A local `just k6` run takes the test lock. `TARGET=lxc` runs k6 on saas-loadgen, so it does not.

## Running k6

k6 scripts live in `loadtest/k6/` (`lib/config.js`, `lib/api.js`, `scenarios/*.js`).
`loadtest/run.sh` (`just k6`) runs one scenario in the `grafana/k6` container against the local
load-test stack's gateway. `outage` proves the respondent flow survives `catalog` being stopped: stop it
yourself once the run starts (see the scenario's header). Results go to Prometheus by remote write, tagged
`testid=<scenario>-<UTC time>`. The summary JSON goes to `loadtest/results/` (gitignored).

- Every request carries a `name` tag (endpoint group, such as `questionnaire-detail`). Never
  tag by URL: UUIDs would create one Prometheus series per row.
- Scenarios read from the `just loadtest-seed` owners. Each VU logs in as `loadtest-<n>@example.com`
  (`OWNERS`, default 5), so seed at least that many. The respondent flow creates a fresh
  questionnaire per submit, so a 409 is a real failure.
- Run one scenario at a time. `run.sh` stops a k6 left behind by an interrupted run.
- `load`, `stress` and `soak` take `MIX=mixed` (default, 47 % writes) or `MIX=read` (mostly reads).
  A cache's value depends heavily on the mix, so compare both.
- They also take `LOGIN=vu` (default: each VU logs in on its first iteration) or `LOGIN=setup` (#50: k6's
  `setup()` logs each owner in once, before the traffic, and a stale token is refreshed, not re-logged-in).
  Every knee before #50 was k6 adding VUs that all logged in at once, a pbkdf2 burst on `catalog`; use
  `LOGIN=setup` to measure past it. Only compare runs with the same `LOGIN`, and say which in a baseline.
- `catalog` (#39) loads `catalog` alone, since the other mixes leave it near idle: `CATALOG_MIX=crud`
  (default: lists, details, `/me`, token refresh, type create/update/delete) or `CATALOG_MIX=login` (one
  login per iteration, the pbkdf2 path). `RATE`/`HOLD` hold a rate; with `MAX_RATE` it steps up as `stress` does.
- k6 sends trends as native histograms (`K6_PROMETHEUS_RW_TREND_AS_NATIVE_HISTOGRAM`, #20), so
  `k6_http_req_duration_seconds` gives true per-minute latency through `rate()`. Runs before that have
  only `k6_http_req_duration_{p95,avg,…}`, calculated since the run began, so they lag and stay raised after a
  stall. Never read those as one minute's latency, and don't compare them with new p95. `just k6-report`
  labels them "since start", and recovers an old run's per-minute mean from `avg × count`, per series,
  since k6 stops sending a series with no new samples and it goes stale after 5 minutes. Its
  `dropped/min` misses a counter's first jump, usually a soak's startup drops, so take totals from the
  run's summary JSON.

## Prometheus and Grafana

- Config lives in `infra/observability/`. Dashboards are generated: edit `grafana/build_dashboards.py`, then
  run `python3 infra/observability/grafana/build_dashboards.py`. `backend/tests/test_observability.py` fails if
  the committed JSON is stale, and also runs promtool on the config and rules (needs Docker).
- Prometheus scrapes each service directly, with a `service` label. On the load-test stack, `/metrics` admits
  only Prometheus's fixed address (`10.95.0.10/32`). A subnet-wide rule would also admit the host, because
  published ports arrive from the subnet's gateway.

## Measuring (`loadtest/baselines/`)

Run `just loadtest-reset` before every measured k6 run, since runs add data and change the numbers (it also
empties the cache). It rsyncs the working tree, so it deploys whatever is checked out. Change one thing at a
time and re-stress.

- Quicker runs: `just k6 stress TARGET=lxc STEP=10 MAX_RATE=500 START_RATE=150` skips the low rates, and to
  compare two configs, `just k6 load TARGET=lxc RATE=<fixed> HOLD=5m` on each, back to back, is quicker and
  less affected by run-to-run variation than comparing knees. Only compare runs with the same settings.
- A full baseline takes two stress runs per mix, for a range, and a 1-hour soak (`DURATION=1h`), which covers
  the 45-minute monolith reference `soak-20261104T055745Z`. Soak for 3 hours only to find where a soak gives
  out. Stop a soak after 5 minutes in a row over 1 % dropped iterations: it won't stop itself.
- Record each baseline as `loadtest/baselines/<date>.md` (`just k6-report <testid>` makes the tables), then add
  it to the `/load-tests` page, which is copied by hand: figures in `frontend/src/lib/loadtestResults.ts`,
  charts in `frontend/src/lib/loadtestCharts.ts`, text in `frontend/src/components/loadtest/LoadTestTabs.tsx`
  (route: `frontend/src/routes/_authed/load-tests.tsx`). Prefer a chart to a bare table. A chart of table
  figures reads them from that table (`cellNumber`), so there is one copy, and the table goes behind
  `TableDetails`. Check any figure written in a chart's end label or aria text against the data. The page needs
  a login but its JS chunk does not, so keep LAN addresses and secrets out of it.
- Tuning knobs: `gunicorn_workers`, `gunicorn_threads` and `conn_max_age` for `catalog`
  (`infra/ansible/group_vars/app.yml`); `dotnet_db_pool_size` (Npgsql's pool) and `dotnet_min_threads` (the
  thread pool's minimum) for `instances` (`group_vars/instances.yml`); `cache_enabled` in both. For a cache-off
  run: `just converge --tags app -e cache_enabled=false`.
