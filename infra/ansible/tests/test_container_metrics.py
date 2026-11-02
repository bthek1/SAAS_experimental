"""roles/common/files/container-metrics.sh against a fake cgroup (#9, Phase 4)."""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "roles/common/files/container-metrics.sh"
GIB = 1024**3


def run(
    tmp_path,
    *,
    cpuset="1,15",
    memory_max="max",
    current=GIB // 2,
    inactive=GIB // 4,
    usage_usec=3009535,
):
    cg = tmp_path / "cgroup"
    cg.mkdir()
    (cg / "cpu.stat").write_text(
        f"usage_usec {usage_usec}\nuser_usec 1836377\n"
        "nr_throttled 2\nthrottled_usec 1500000\n"
    )
    (cg / "cpuset.cpus.effective").write_text(f"{cpuset}\n")
    (cg / "memory.current").write_text(f"{current}\n")
    (cg / "memory.max").write_text(f"{memory_max}\n")
    (cg / "memory.stat").write_text(f"anon 1000\nfile 2000\ninactive_file {inactive}\n")
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:        2097152 kB\nMemFree:  1 kB\n")
    out = tmp_path / "container.prom"
    subprocess.run(  # noqa: S603
        ["sh", str(SCRIPT), str(out)],  # noqa: S607
        env={"CGROUP_ROOT": str(cg), "MEMINFO": str(meminfo), "PATH": "/usr/bin:/bin"},
        check=True,
    )
    return {
        line.split()[0]: float(line.split()[1])
        for line in out.read_text().splitlines()
        if line and not line.startswith("#")
    }


def test_cpu_counters_in_seconds(tmp_path):
    metrics = run(tmp_path)
    assert metrics["container_cpu_usage_seconds_total"] == pytest.approx(3.009535)
    assert metrics["container_cpu_throttled_seconds_total"] == pytest.approx(1.5)


def test_large_counters_keep_microsecond_precision(tmp_path):
    # awk's default %.6g would print 1.23457e+06 here: whole seconds lost.
    cg_usage = 1_234_567_891_234  # usec, about 14 days of one core
    metrics = run(tmp_path, usage_usec=cg_usage)
    assert metrics["container_cpu_usage_seconds_total"] == pytest.approx(
        1_234_567.891234, abs=1e-6
    )


@pytest.mark.parametrize(
    ("cpuset", "cores"), [("1,15", 2), ("0-3", 4), ("0-3,8,10-11", 7), ("5", 1)]
)
def test_cpu_limit_counts_the_cpuset(tmp_path, cpuset, cores):
    assert run(tmp_path, cpuset=cpuset)["container_cpu_limit_cores"] == cores


def test_memory_limit_falls_back_to_lxcfs_meminfo(tmp_path):
    # Inside the container's cgroup namespace, memory.max reads "max".
    assert run(tmp_path)["container_memory_limit_bytes"] == 2 * GIB


def test_memory_limit_from_the_cgroup_when_set(tmp_path):
    metrics = run(tmp_path, memory_max=str(GIB))
    assert metrics["container_memory_limit_bytes"] == GIB


def test_working_set_excludes_inactive_page_cache(tmp_path):
    metrics = run(tmp_path, current=GIB, inactive=GIB // 4)
    assert metrics["container_memory_usage_bytes"] == GIB
    assert metrics["container_memory_working_set_bytes"] == GIB - GIB // 4


def test_working_set_never_negative(tmp_path):
    metrics = run(tmp_path, current=100, inactive=200)
    assert metrics["container_memory_working_set_bytes"] == 0
