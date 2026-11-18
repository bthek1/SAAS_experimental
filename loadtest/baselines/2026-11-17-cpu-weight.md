# Load-test baseline: 2026-11-17, CPU weight 4096 on the request path

Plan: #56. Code: `3ecdf8c` (`instances` on .NET, the same code as the morning's run) plus the uncommitted #56
Pulumi change, applied with `just infra-up`: saas-catalog, saas-db, saas-loadgen, saas-cache, saas-instances and
saas-gateway at Proxmox `cpuunits` 4096, saas-monitor at 1024. Every container had been at the provider's 1024.

**Summary.** **No effect.** CPU-pressure wait, the number the weight was meant to lower, is unchanged on every
container, and latency is within run-to-run variation (slightly worse), on a host that was quieter than in the
morning. Weight only orders a contended core's queue against other guests; this wait does not come from them.

## Fixed rate, before and after

`just k6 load TARGET=lxc RATE=200 HOLD=5m MIX=mixed` (`LOGIN=vu`), each from its own `just loadtest-reset`.
CPU wait is `rate(node_pressure_cpu_waiting_seconds_total[5m])` at the run's end; host load is `node_load1`
averaged over the same 5 minutes.

| Run | Weight | Host load | Requests | Mean | p95 | CPU wait, instances | CPU wait, db | Dropped | Failed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `load-20261117T081104Z` | 1024 | 5.9 | 110,623 | 2.47 ms | 5.50 ms | 0.127 s/s | 0.019 s/s | 0 | 0 |
| `load-20261117T161649Z` | 4096 | 4.7 | 110,141 | 2.88 ms | 5.84 ms | 0.123 s/s | 0.029 s/s | 17 | 0 |

- **CPU used is the same** (instances 25 to 27 %, saas-db 11 to 12 %), so both runs did the same work.
- **The 17 dropped iterations** were all in minute 1, as VUs logged in, and minute 2's slowest group p95 reached
  591 ms once. Minutes 3 to 6 were steady at 2.7 ms mean.
- **Why it could not help:** on cgroup v2 Proxmox's default weight is 100, so if the other guests use it, 1024
  was already about 10 times theirs. saas-instances waits for a CPU at 25 % of its 2 cores, with host load under 6;
  the likeliest cause is its own threads queueing on its 2-core cpuset, which no weight between guests changes.
  Not proven.

## How far to trust it

- **One run each, at a low rate.** A stress run, where contention is higher, was not repeated.
- **Host load was not controlled**, but it was lower in the run with the higher weight, which should have helped
  it.

## Still open

- **Pin cores on the host** (`lxc.cgroup2.cpuset.cpus` in `/etc/pve/lxc/<id>.conf`, other guests kept off them).
  Pulumi's provider cannot set a cpuset (#56).
- The weight stays at 4096: harmless, and reverting it is one Pulumi change.
