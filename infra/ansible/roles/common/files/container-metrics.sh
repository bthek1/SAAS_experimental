#!/bin/sh
# This container's CPU and memory from its own cgroup (v2), in Prometheus text
# format, for node_exporter's textfile collector (#9, Phase 4).
#
# Why not node_exporter's own CPU metrics: inside an LXC, /proc/stat lists the
# container's cores but counts everything the host runs on them (measured: an
# idle container read 16 % busy). The cgroup counts only this container.
# The CPU limit is the cpuset (Proxmox "cores"); memory.max reads "max" inside
# the namespace, so the limit comes from lxcfs's /proc/meminfo.
set -eu
# Seconds are printed with %.6f: awk's default (%.6g, six significant digits)
# would round a CPU counter past ~10^6 s by whole seconds and wreck rate().
out="$1"
# Overridable for tests (infra/ansible/tests/test_container_metrics.py).
cg="${CGROUP_ROOT:-/sys/fs/cgroup}"
meminfo="${MEMINFO:-/proc/meminfo}"

usage_usec=$(awk '$1 == "usage_usec" {print $2}' "$cg/cpu.stat")
throttled_usec=$(awk '$1 == "throttled_usec" {print $2}' "$cg/cpu.stat")
cores=$(awk -F, '{n = 0; for (i = 1; i <= NF; i++) { split($i, r, "-"); n += (r[2] == "" ? 1 : r[2] - r[1] + 1) } print n}' "$cg/cpuset.cpus.effective")
mem=$(cat "$cg/memory.current")
# memory.current includes page cache (file-backed, reclaimable). The working set
# subtracts the inactive part of it, as cAdvisor does: what the limit really bites.
inactive_file=$(awk '$1 == "inactive_file" {print $2}' "$cg/memory.stat")
working_set=$((mem > inactive_file ? mem - inactive_file : 0))
mem_max=$(cat "$cg/memory.max")
if [ "$mem_max" = max ]; then
  mem_max=$(awk '$1 == "MemTotal:" {print $2 * 1024}' "$meminfo")
fi

tmp="$out.$$"
cat > "$tmp" <<METRICS
# HELP container_cpu_usage_seconds_total CPU time used by this container (cgroup).
# TYPE container_cpu_usage_seconds_total counter
container_cpu_usage_seconds_total $(awk "BEGIN {printf \"%.6f\", $usage_usec / 1000000}")
# HELP container_cpu_throttled_seconds_total Time this container was throttled (cgroup).
# TYPE container_cpu_throttled_seconds_total counter
container_cpu_throttled_seconds_total $(awk "BEGIN {printf \"%.6f\", $throttled_usec / 1000000}")
# HELP container_cpu_limit_cores CPUs this container may use (cpuset).
# TYPE container_cpu_limit_cores gauge
container_cpu_limit_cores $cores
# HELP container_memory_usage_bytes Memory charged to this container (cgroup).
# TYPE container_memory_usage_bytes gauge
container_memory_usage_bytes $mem
# HELP container_memory_working_set_bytes Memory in use minus inactive page cache.
# TYPE container_memory_working_set_bytes gauge
container_memory_working_set_bytes $working_set
# HELP container_memory_limit_bytes This container's memory limit.
# TYPE container_memory_limit_bytes gauge
container_memory_limit_bytes $mem_max
METRICS
mv "$tmp" "$out"
