"""The Pulumi resources: the load-test LXC containers (#9, Phase 3).

Pulumi creates bare, unprivileged Ubuntu 24.04 containers with root SSH by key
and a fixed address. Ansible (Phase 4) installs and configures everything on
them, so nothing here runs inside a container.

Config lives under the ``saas:`` namespace (see Pulumi.loadtest.yaml.example).
The provider reads ``proxmoxve:endpoint`` / ``proxmoxve:apiToken`` itself.
Secrets are generated here and kept encrypted in the stack state, never in a
file in the repo.
"""

from __future__ import annotations

from dataclasses import dataclass

import pulumi
import pulumi_proxmoxve as proxmox
import pulumi_random as random
import pulumi_tls as tls

from .topology import PREVIOUS_NAMES, Guest, Network, build

TAGS = ["saas-experimental", "loadtest", "pulumi"]


@dataclass
class Stack:
    guests: dict[str, Guest]
    containers: dict[str, proxmox.ct.Container]
    secrets: dict[str, pulumi.Output]


def load_network(cfg: pulumi.Config) -> Network:
    raw = cfg.require_object("network")
    return Network(
        cidr=raw["cidr"],
        gateway=raw["gateway"],
        bridge=raw.get("bridge", "vmbr0"),
        dns=tuple(raw.get("dns", [raw["gateway"]])),
        admin_hosts=tuple(raw.get("adminHosts", [])),
    )


def _password(name: str, length: int = 32) -> pulumi.Output:
    # Alphanumeric only: these land in URLs (DATABASE_URL) and env files.
    return random.RandomPassword(name, length=length, special=False).result


def generate_secrets() -> dict[str, pulumi.Output]:
    # RS256: catalog holds both halves, and instances only the public one (#13).
    jwt = tls.PrivateKey("jwt-key", algorithm="RSA", rsa_bits=2048)
    return {
        "jwt_signing_key": jwt.private_key_pem,
        "jwt_verifying_key": jwt.public_key_pem,
        "catalog_to_instances_token": _password("catalog-to-instances-token", 48),
        "instances_to_catalog_token": _password("instances-to-catalog-token", 48),
        "instances_db_password": _password("instances-db-password"),
        "db_password": _password("db-password"),
        "django_secret_key": _password("django-secret-key", 64),
        "grafana_admin_password": _password("grafana-admin-password", 24),
        "loadtest_owner_password": _password("loadtest-owner-password", 24),
        "redis_password": _password("redis-password"),
    }


def container(
    guest: Guest,
    *,
    node: str,
    network: Network,
    datastore: str,
    template: str,
    ssh_keys: list[str],
    pool: str | None,
) -> proxmox.ct.Container:
    return proxmox.ct.Container(
        guest.name,
        node_name=node,
        vm_id=guest.vmid,
        pool_id=pool,
        description=(
            f"SAAS_experimental load test: {guest.role} (#9). Managed by Pulumi."
        ),
        tags=[*TAGS, guest.role],
        # Unprivileged: container root is an unprivileged user on the host.
        # nesting is the Proxmox default, which systemd in Ubuntu 24.04 needs.
        # keyctl stays off, so Docker cannot run inside (Phase 4 installs natively).
        unprivileged=True,
        features={"nesting": True, "keyctl": False},
        cpu={"cores": guest.cores},
        memory={"dedicated": guest.memory_mb, "swap": 512},
        disk={"datastore_id": datastore, "size": guest.disk_gb},
        operating_system={"template_file_id": template, "type": "ubuntu"},
        network_interfaces=[{"name": "eth0", "bridge": network.bridge}],
        initialization={
            "hostname": guest.name,
            "ip_configs": [
                {"ipv4": {"address": guest.address, "gateway": network.gateway}}
            ],
            "dns": {"servers": list(network.dns)},
            # No root password: SSH by key only.
            "user_account": {"keys": ssh_keys},
        },
        start_on_boot=True,
        started=True,
        opts=pulumi.ResourceOptions(
            aliases=[pulumi.Alias(name=PREVIOUS_NAMES[guest.role])]
            if guest.role in PREVIOUS_NAMES
            else []
        ),
    )


def run() -> Stack:
    cfg = pulumi.Config("saas")
    network = load_network(cfg)
    guests = build(network, cfg.get_object("sizes"))
    ssh_keys = cfg.require_object("sshPublicKeys")
    if not ssh_keys:
        raise ValueError("saas:sshPublicKeys is empty: nothing could log in")
    containers = {
        role: container(
            guest,
            node=cfg.require("node"),
            network=network,
            datastore=cfg.get("datastore") or "local-lvm",
            template=cfg.require("template"),
            ssh_keys=ssh_keys,
            pool=cfg.get("pool"),
        )
        for role, guest in guests.items()
    }
    secrets = generate_secrets()

    # Read by the Ansible inventory (Phase 4) and loadtest/run.sh.
    pulumi.export(
        "guests",
        {
            role: {"name": g.name, "vmid": g.vmid, "ip": g.ip}
            for role, g in guests.items()
        },
    )
    pulumi.export("ips", {role: g.ip for role, g in guests.items()})
    pulumi.export("ssh_user", "root")
    pulumi.export("admin_hosts", list(network.admin_hosts))
    # The LAN: Grafana is open to it (infra/ansible/group_vars/monitor.yml).
    pulumi.export("network_cidr", network.cidr)
    pulumi.export("grafana_url", f"http://{guests['monitor'].ip}:3000")
    pulumi.export("prometheus_url", f"http://{guests['monitor'].ip}:9090")
    for name, value in secrets.items():
        pulumi.export(name, pulumi.Output.secret(value))
    return Stack(guests=guests, containers=containers, secrets=secrets)
