"""The load-test containers, their ids, addresses and sizes (#9, Phase 3).

Proxmox guest ids 241-249 belong to this repo, and a container's address is
its id as the last octet (saas-catalog 241 → x.y.z.241), so the id in the Proxmox
UI is also where to SSH. VMs and containers share one id space on the host:
220-240 belong to ~/kubernates_project and are refused here.

Ids are fixed per role, never positional. kubernates_project numbered its VMs
by list position, so inserting a role renumbered every later VM, and Pulumi
*replaced* them, data included. A new role here takes the next free id.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

# `app` is the catalog service (#13). It keeps its role and id, so Pulumi never replaces it.
# The container is called saas-catalog (#21). PREVIOUS_NAMES keeps its Pulumi resource:
# without the alias, a new name would destroy and recreate it, data included.
NAMES = {"app": "saas-catalog"}
PREVIOUS_NAMES = {"app": "saas-app"}
GUEST_IDS = {
    "app": 241,
    "db": 242,
    "monitor": 243,
    "loadgen": 244,
    "cache": 245,
    "instances": 246,
    "gateway": 247,
}
ROLES = tuple(GUEST_IDS)
ID_RANGE = range(241, 250)
RESERVED = range(220, 241)  # ~/kubernates_project's VMs

# The host had ~24 GB available on 2026-11-02 (63 GB total). About 8 GB here.
DEFAULT_SIZES = {
    # catalog keeps 2 cores although it is mostly idle: logins hash passwords, and on
    # 1 core they were ~10x slower under load (1.4 s -> 14 s), for a hot-path gain on
    # instances (1 + 3) that was within run-to-run variation (#24, Phase 3).
    "app": {"cores": 2, "memoryMb": 2048, "diskGb": 8},
    "db": {"cores": 2, "memoryMb": 1024, "diskGb": 10},
    "monitor": {"cores": 1, "memoryMb": 1024, "diskGb": 10},
    # k6 holds about 1 MB per VU; stress tops out at 300 VUs.
    "loadgen": {"cores": 2, "memoryMb": 1024, "diskGb": 4},
    # Redis holds up to 256 MB (maxmemory) and writes nothing to disk (#11).
    "cache": {"cores": 1, "memoryMb": 512, "diskGb": 4},
    "instances": {"cores": 2, "memoryMb": 2048, "diskGb": 8},
    # nginx only.
    "gateway": {"cores": 1, "memoryMb": 512, "diskGb": 4},
}


@dataclass(frozen=True)
class Network:
    cidr: str
    gateway: str
    bridge: str = "vmbr0"
    dns: tuple[str, ...] = ()
    admin_hosts: tuple[str, ...] = ()

    @property
    def prefix(self) -> int:
        return ipaddress.ip_network(self.cidr).prefixlen


@dataclass(frozen=True)
class Guest:
    role: str
    vmid: int
    ip: str
    cores: int
    memory_mb: int
    disk_gb: int
    prefix: int

    @property
    def name(self) -> str:
        return NAMES.get(self.role, f"saas-{self.role}")

    @property
    def address(self) -> str:
        return f"{self.ip}/{self.prefix}"


def check_vmid(vmid: int) -> None:
    if vmid in RESERVED:
        raise ValueError(f"guest id {vmid} belongs to kubernates_project (220-240)")
    if vmid not in ID_RANGE:
        raise ValueError(f"guest id {vmid} is outside this repo's range 241-249")


def ip_for(network: Network, vmid: int) -> str:
    net = ipaddress.ip_network(network.cidr)
    if not net.is_private:
        raise ValueError(f"{network.cidr} is not a private network")
    ip = net.network_address + vmid
    if ip not in net or ip in (net.network_address, net.broadcast_address):
        raise ValueError(f"guest id {vmid} gives {ip}, not a host in {network.cidr}")
    if str(ip) == network.gateway:
        raise ValueError(f"guest id {vmid} would take the gateway's address {ip}")
    return str(ip)


def build(network: Network, sizes: dict | None = None) -> dict[str, Guest]:
    unknown = set(sizes or {}) - set(ROLES)
    if unknown:
        raise ValueError(f"sizes for unknown roles: {sorted(unknown)}")
    guests = {}
    for role, vmid in GUEST_IDS.items():
        check_vmid(vmid)
        size = {**DEFAULT_SIZES[role], **(sizes or {}).get(role, {})}
        guests[role] = Guest(
            role=role,
            vmid=vmid,
            ip=ip_for(network, vmid),
            cores=int(size["cores"]),
            memory_mb=int(size["memoryMb"]),
            disk_gb=int(size["diskGb"]),
            prefix=network.prefix,
        )
    return guests
