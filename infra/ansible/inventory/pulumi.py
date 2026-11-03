#!/usr/bin/env python3
"""Ansible dynamic inventory from the Pulumi stack (#9, Phase 4).

    ansible-inventory -i inventory/pulumi.py --graph

Reads `pulumi stack output --json --show-secrets` for the `loadtest` stack
(infra/pulumi/), with this repo's own state backend and passphrase, the same
way the justfile does. One group per role (app, db, monitor, loadgen, cache), one host
each. Stack secrets become variables on `all`, so nothing secret is written to
a file in the repo.

⚠️ Refuses any address that is not private: these playbooks open firewall
holes and install an unthrottled backend.
"""

from __future__ import annotations

import ipaddress
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATE = Path.home() / ".pulumi-state"
SECRETS = (
    "db_password",
    "django_secret_key",
    "grafana_admin_password",
    "loadtest_owner_password",
    "redis_password",
)


def stack_outputs() -> dict:
    env = {
        **os.environ,
        "PULUMI_BACKEND_URL": f"file://{STATE / 'saas-experimental'}",
        "PULUMI_CONFIG_PASSPHRASE_FILE": os.environ.get(
            "PULUMI_CONFIG_PASSPHRASE_FILE",
            str(STATE / "saas-experimental.passphrase"),
        ),
        "VIRTUAL_ENV": "",
    }
    cmd = [
        "pulumi",
        "-C",
        str(ROOT / "infra" / "pulumi"),
        "--stack",
        "loadtest",
        "stack",
        "output",
        "--json",
        "--show-secrets",
    ]
    # Fixed argv: pulumi from PATH, our own stack.
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        sys.exit(f"pulumi stack output failed:\n{result.stderr}")
    return json.loads(result.stdout)


def build(outputs: dict) -> dict:
    guests = outputs["guests"]
    admin_hosts = outputs.get("admin_hosts", [])
    for address in [g["ip"] for g in guests.values()] + admin_hosts:
        if not ipaddress.ip_address(address).is_private:
            sys.exit(f"refusing inventory: {address} is not a private address")
    lan_cidr = outputs["network_cidr"]
    if not ipaddress.ip_network(lan_cidr).is_private:
        sys.exit(f"refusing inventory: {lan_cidr} is not a private network")
    inventory: dict = {
        "_meta": {
            "hostvars": {
                g["name"]: {"ansible_host": g["ip"], "guest_ip": g["ip"], "role": role}
                for role, g in guests.items()
            }
        },
        "all": {
            "children": list(guests),
            "vars": {
                "ansible_user": outputs.get("ssh_user", "root"),
                "guest_ips": {role: g["ip"] for role, g in guests.items()},
                "admin_hosts": admin_hosts,
                "lan_cidr": lan_cidr,
                **{name: outputs[name] for name in SECRETS},
            },
        },
    }
    for role, g in guests.items():
        inventory[role] = {"hosts": [g["name"]]}
    return inventory


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--host":
        print("{}")  # noqa: T201 - everything is in _meta
        return
    print(json.dumps(build(stack_outputs()), indent=2))  # noqa: T201


if __name__ == "__main__":
    main()
