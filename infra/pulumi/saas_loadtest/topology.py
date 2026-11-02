"""The load-test containers, their ids, addresses and sizes (#9, Phase 3).

Proxmox guest ids 241-249 belong to this repo, and a container's address is
its id as the last octet (saas-app 241 → x.y.z.241), so the id in the Proxmox
UI is also where to SSH. VMs and containers share one id space on the host:
220-240 belong to ~/kubernates_project and are refused here.

Ids are fixed per role, never positional. kubernates_project numbered its VMs
by list position, so inserting a role renumbered every later VM, and Pulumi
*replaced* them, data included. A new role here takes the next free id.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

GUEST_IDS = {"app": 241, "db": 242, "monitor": 243, "loadgen": 244}
ROLES = tuple(GUEST_IDS)
ID_RANGE = range(241, 250)
RESERVED = range(220, 241)  # ~/kubernates_project's VMs

# The host had ~24 GB available on 2026-11-02 (63 GB total). About 5 GB here.
DEFAULT_SIZES = {
    "app": {"cores": 2, "memoryMb": 2048, "diskGb": 8},
    "db": {"cores": 2, "memoryMb": 1024, "diskGb": 10},
    "monitor": {"cores": 1, "memoryMb": 1024, "diskGb": 10},
    # k6 holds about 1 MB per VU; stress tops out at 300 VUs.
    "loadgen": {"cores": 2, "memoryMb": 1024, "diskGb": 4},
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
        return f"saas-{self.role}"

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
