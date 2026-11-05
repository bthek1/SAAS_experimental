# Load-test baseline: 2026-11-04, catalog + instances split

Plan: #13, Phase 5 (#18). Split code: `8daa08d`. Monolith code: `2e58adf` (`main`).

**Summary.** At the same fixed rates, the split costs no measurable latency or CPU, despite the extra gateway hop. Respondents kept working while `catalog` was stopped: 900 of 900 opens and 900 of 900 submits succeeded. Peak capacity did not clearly move: one mixed stress run reached ~581 req/s, against ~430, ~497 and ~573 on the monolith, which is within their spread. The real cost is what has to run: 5 app-tier cores instead of 2, and about twice the memory in use. The extra cores are not what carried the load: `instances` did about 90 % of the app-tier work, on the same 2 cores the monolith had.

## The two deploys

Same host, seed and k6 commands as [2026-11-03-redis-cache.md](2026-11-03-redis-cache.md): 20 owners × 200 questionnaires, `just loadtest-reset` before each run. saas-db (2 cores, 1 GB) and saas-cache (1 core, 512 MB) are unchanged.

| | Monolith | Split |
|---|---|---|
| Path | k6 → saas-app | k6 → saas-gateway → saas-app or saas-instances |
| saas-gateway | none | 1 core, 512 MB, nginx |
| saas-app | 2 cores, 2 GB, 5 workers × 4 threads, everything | 2 cores, 2 GB, 3 workers × 4 threads, `catalog` |
| saas-instances | none | 2 cores, 2 GB, 5 workers × 4 threads, `instances` |
| **App tier total** | **2 cores, 2 GB, 20 threads** | **5 cores, 4.5 GB, 32 threads** |

The monolith was deployed from `main` on the same containers for the fixed-rate runs, and the split was deployed right after them. The monolith stress runs are older (`94b9645`, from [2026-11-04-dashboard.md](2026-11-04-dashboard.md)). The only backend commit between `94b9645` and `2e58adf` changed reporting. They ran the same command, but not back to back with the split.

## Holding a fixed rate

`just k6 load TARGET=lxc RATE=200 HOLD=5m`, one run each. 0 failed and 0 dropped in all four.

| | Mixed, monolith | Mixed, split | Read, monolith | Read, split |
|---|---|---|---|---|
| Run | `load-20261104T173501Z` | `load-20261104T180254Z` | `load-20261104T174207Z` | `load-20261104T181005Z` |
| Requests | 110,315 | 110,543 | 75,854 | 76,091 |
| Mean | 4.82 ms | 4.73 ms | 4.16 ms | 3.80 ms |
| p95, all requests | 10.16 ms | 10.17 ms | 8.94 ms | 8.09 ms |
| Max | 164 ms | 115 ms | 133 ms | 115 ms |
| App-tier CPU, in cores | 0.85 | 0.88 | 0.69 | 0.66 |
| saas-db CPU, in cores | 0.21 | 0.19 | 0.13 | 0.12 |
| Postgres connections, most sampled | 20 | 25 | 20 | 25 |
| App-tier memory in use | 605 MB | 1,120 MB | 619 MB | 1,264 MB |

App-tier CPU and memory are from one reading, 5 minutes into each run: CPU is the 3-minute rate, and memory is the working set.

| Split, by container | gateway | saas-app (`catalog`) | saas-instances |
|---|---|---|---|
| CPU in cores, mixed / read | 0.03 / 0.02 | 0.05 / 0.07 | 0.80 / 0.57 |
| Memory in use, mixed / read | 77 / 78 MB | 417 / 425 MB | 626 / 761 MB |

- **The hop cost nothing visible.** All the differences are small enough to be run-to-run variation, and the split's read run being slightly faster is not a gain to rely on. One run each cannot resolve a difference this small.
- **`instances` does almost all the work.** Under this traffic, `catalog` sits at about 3 % of its 2 cores.

## Stress

`just k6 stress TARGET=lxc STEP=10 STEP_TIME=1m MAX_RATE=500 START_RATE=150`, plus `START_RATE=200 MIX=read` for read. Exit 99 is how a stress run ends. Both split runs stopped on k6's limit of 1,000 dropped iterations.

| | Mixed, split | Read, split |
|---|---|---|
| Run | `stress-20261104T181714Z` | `stress-20261104T184104Z` |
| Last clean minute | ~581 req/s | ~431 req/s |
| saas-instances / saas-db CPU there | 79 % / 24 % | 66 % / 12 % |
| Requests / failed / dropped | 560,746 / 1 / 1,183 | 419,640 / 0 / 1,244 |

Mixed traffic at matching rates, against the one monolith run with true per-minute p95 (`stress-20261104T080836Z`). "Busiest app CPU" is saas-app on the monolith and saas-instances on the split:

| req/s, monolith / split | Mean | Slowest group p95 | Django p95 | Busiest app CPU |
|---|---|---|---|---|
| 350 / 358 | 5.3 / 5.0 ms | 25 / 23 ms | 12 / 10 ms | 48 / 44 % |
| 433 / 432 | 6.3 / 6.5 ms | 39 / 41 ms | 18 / 18 ms | 60 / 56 % |
| 476 / 485 | 7.3 / 7.6 ms | 50 / 54 ms | 21 / 21 ms | 67 / 63 % |
| 546 / 549 | 10.7 / 14.2 ms | 76 / 85 ms | 24 / 33 ms | 77 / 74 % |
| 573 / 581 | 15.1 / 18.2 ms | 98 / 108 ms | 36 / 42 ms | 82 / 79 % |

- **Capacity is not shown to have changed.** The monolith's own range is ~430 to ~573 req/s on identical settings, and this is one run. The top two rows lean slightly against the split, but they sit close to where each run broke.
- **Read traffic is not comparable.** ~431 req/s is one run. The only monolith read knee, ~459 req/s, is from [2026-11-03-redis-cache.md](2026-11-03-redis-cache.md), before the dashboard fixes, and was judged on a different latency figure.
- **The break looks the same as before.** Latency was steady, then within 15 seconds k6 went from a handful of active VUs to its limit of 300, with CPU to spare. So the split neither caused nor cured the sudden collapses that [2026-11-04-dashboard.md](2026-11-04-dashboard.md) left open.
- **One request failed, in the mixed run.** nginx logged two "connection reset by peer" errors from saas-instances: one on `GET /api/batteries/` about two minutes before the break, and one on a `PATCH` seconds before it. systemd's journal has no warnings at either time. k6 counted one failure. The cause was not found. It is the first failed request across the runs on the results page, so watch for it in later runs.

## Outage

`just k6 outage TARGET=lxc RATE=5 DURATION=180` (`outage-20261104T175845Z`), with `saas-relay` and `saas-app` stopped 45 seconds after launch and restarted after k6 finished. Prometheus saw `catalog` down from about 60 seconds into the run until its end, about two-thirds of it.

| | Result |
|---|---|
| Share-link opens | 900 of 900 |
| Submits | 900 of 900 |
| All requests | 2,752, 0 failed, mean 3.4 ms, p95 5.7 ms |
| Log in while `catalog` is down | 502 from the gateway, as expected |
| Log in after it returns | 200 |

The other direction, with `saas-instances` stopped: three type edits and one type create all returned success.

| | Result |
|---|---|
| While it was down | 4 events pending, the oldest 9.8 s old after 12 s |
| After it restarted | `app_outbox_pending_events` at 0 within 24 s, the first reading to show it |
| In `instances` | The last edit's title |
| `app_retire_failures_total` | 0 |

Deleting a type while `instances` is down (503) and a deactivated user being refused on both services were checked on an isolated Compose stack in Phase 4, not on this deploy.

## How far to trust it

- **One run per fixed-rate setting and one stress run per mix on the split.** Stress results have varied by about 140 req/s on identical settings. The cause is unknown, and the other guests on this host were not ruled out.
- **Short runs from reset data.** No soak was run on the split, so growth in `instances`' rows is untested here. It holds the same tables and queries as the monolith did, so a change is not expected, but that is not measured.
- **Memory is one reading, not a peak.** saas-instances read 626 MB in the mixed run and 761 MB in the read run, and why they differ was not looked into.
- **Everything shares one Proxmox host.** A gateway on its own host would add real network latency that this hop barely shows.

## Is the split worth it?

The numbers don't argue for stopping at Phase 3 (the modular monolith with RS256). The split costs no measurable latency or CPU here. What it adds is that respondents survive a `catalog` outage, and that the services can be deployed separately. What it costs is two more containers, about twice the memory, and the outbox to watch. Whether that trade is right depends on how much those availability gains matter, which load tests can't answer.

## Still open

- **Resize the app tier.** `catalog` uses about 3 % of its 2 cores here, so it could likely give up a core and some workers. `instances` is the part to give more cores to. Neither has been tried.
- **A soak on the split,** to its stop rule.
- **The two connection resets** from saas-instances, and the sudden collapses generally.
- **`MIX=read` stress on the monolith** at current code, if a read comparison ever matters.
