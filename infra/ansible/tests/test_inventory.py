"""inventory/pulumi.py (#9, Phase 4): groups, variables, private addresses only."""

import importlib.util
from pathlib import Path

import pytest

INVENTORY = Path(__file__).resolve().parents[1] / "inventory" / "pulumi.py"
spec = importlib.util.spec_from_file_location("pulumi_inventory", INVENTORY)
assert spec
assert spec.loader
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)

SECRETS = {name: f"secret-{name}" for name in inventory.SECRETS}


def outputs(**overrides):
    guests = {
        role: {"name": f"saas-{role}", "vmid": vmid, "ip": f"192.168.2.{vmid}"}
        for role, vmid in {
            "app": 241,
            "db": 242,
            "monitor": 243,
            "loadgen": 244,
            "cache": 245,
            "instances": 246,
            "gateway": 247,
        }.items()
    }
    return {
        "guests": guests,
        "ssh_user": "root",
        "admin_hosts": ["192.168.2.106"],
        "network_cidr": "192.168.2.0/24",
        **SECRETS,
        **overrides,
    }


def test_one_group_per_role_one_host_each():
    built = inventory.build(outputs())
    for role in ("app", "db", "monitor", "loadgen", "cache", "instances", "gateway"):
        assert built[role] == {"hosts": [f"saas-{role}"]}
    hostvars = built["_meta"]["hostvars"]
    assert hostvars["saas-app"] == {
        "ansible_host": "192.168.2.241",
        "guest_ip": "192.168.2.241",
        "role": "app",
    }


def test_shared_variables_and_secrets_on_all():
    variables = inventory.build(outputs())["all"]["vars"]
    assert variables["ansible_user"] == "root"
    assert variables["guest_ips"]["db"] == "192.168.2.242"
    assert variables["admin_hosts"] == ["192.168.2.106"]
    assert variables["lan_cidr"] == "192.168.2.0/24"
    for name, value in SECRETS.items():
        assert variables[name] == value


def test_refuses_a_public_guest_address():
    bad = outputs()
    bad["guests"]["app"]["ip"] = "8.8.8.8"
    with pytest.raises(SystemExit, match=r"8\.8\.8\.8 is not a private address"):
        inventory.build(bad)


def test_refuses_a_public_admin_host():
    with pytest.raises(SystemExit, match="not a private address"):
        inventory.build(outputs(admin_hosts=["1.1.1.1"]))


def test_refuses_a_public_lan():
    with pytest.raises(SystemExit, match="not a private network"):
        inventory.build(outputs(network_cidr="8.8.8.0/24"))
