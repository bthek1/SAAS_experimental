"""The Pulumi program under mocks: no Proxmox, no network.

`pulumi.runtime.set_mocks` answers every resource registration with its own
inputs and records it, so the tests assert on what *would* be created.
"""

from __future__ import annotations

import ipaddress
import json

import pulumi

# How the engine wire format marks a secret value.
SECRET_SIG = "4dabf18193072939515e22adb298388d"
CONTAINER = "proxmoxve:CT/container:Container"
TEMPLATE = "local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
KEY = "ssh-ed25519 AAAAC3Nza test@workstation"


def _plain(value):
    if isinstance(value, dict) and SECRET_SIG in value:
        return _plain(value["value"])
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


class Mocks(pulumi.runtime.Mocks):
    def __init__(self) -> None:
        self.resources: list[tuple[str, str, dict]] = []

    def new_resource(self, args: pulumi.runtime.MockResourceArgs):
        inputs = _plain(args.inputs)
        self.resources.append((args.typ, args.name, inputs))
        outputs = dict(inputs)
        if args.typ == "random:index/randomPassword:RandomPassword":
            outputs["result"] = "p" * int(inputs["length"])
        if args.typ == "tls:index/privateKey:PrivateKey":
            outputs["private_key_pem"] = "private"
            outputs["public_key_pem"] = "public"
        return f"{args.name}-id", outputs

    def call(self, args: pulumi.runtime.MockCallArgs):  # noqa: ARG002 (Mocks API)
        return {}

    def containers(self) -> dict[str, dict]:
        return {
            name: inputs for typ, name, inputs in self.resources if typ == CONTAINER
        }


MOCKS = Mocks()
pulumi.runtime.set_mocks(MOCKS, project="saas-loadtest", stack="test", preview=False)
pulumi.runtime.set_all_config(
    {
        "saas:node": "pve",
        "saas:pool": "saas-loadtest",
        "saas:template": TEMPLATE,
        "saas:network": json.dumps(
            {
                "cidr": "192.168.2.0/24",
                "gateway": "192.168.2.1",
                "adminHosts": ["192.168.2.106"],
            }
        ),
        "saas:sshPublicKeys": json.dumps([KEY]),
    }
)

from saas_loadtest import program  # noqa: E402  (mocks must be installed first)

STACK = program.run()


def _after_all(check):
    """Run `check` once every container is registered."""
    return pulumi.Output.all(*(c.id for c in STACK.containers.values())).apply(
        lambda _: check()
    )


@pulumi.runtime.test
def test_the_containers_and_nothing_else_on_proxmox():
    def check():
        assert sorted(MOCKS.containers()) == [
            "saas-cache",
            "saas-catalog",
            "saas-db",
            "saas-gateway",
            "saas-instances",
            "saas-loadgen",
            "saas-mongo",
            "saas-monitor",
        ]
        proxmox = {typ for typ, _, _ in MOCKS.resources if typ.startswith("proxmoxve:")}
        assert proxmox == {CONTAINER}

    return _after_all(check)


@pulumi.runtime.test
def test_ids_and_private_static_addresses():
    def check():
        for name, ct in MOCKS.containers().items():
            vmid = int(ct["vmId"])
            assert vmid in range(241, 250), name
            configs = ct["initialization"]["ipConfigs"]
            assert configs == [
                {"ipv4": {"address": f"192.168.2.{vmid}/24", "gateway": "192.168.2.1"}}
            ]
            assert ipaddress.ip_address(f"192.168.2.{vmid}").is_private
            assert len(ct["networkInterfaces"]) == 1

    return _after_all(check)


@pulumi.runtime.test
def test_unprivileged_and_no_docker_inside():
    def check():
        for name, ct in MOCKS.containers().items():
            assert ct["unprivileged"] is True, name
            # nesting: systemd needs it. keyctl off: Docker cannot run inside.
            assert ct["features"] == {"nesting": True, "keyctl": False}, name

    return _after_all(check)


@pulumi.runtime.test
def test_ssh_by_key_only_from_the_template():
    def check():
        for name, ct in MOCKS.containers().items():
            account = ct["initialization"]["userAccount"]
            assert account == {"keys": [KEY]}, name  # no password
            assert ct["operatingSystem"] == {
                "templateFileId": TEMPLATE,
                "type": "ubuntu",
            }
            assert ct["poolId"] == "saas-loadtest"
            assert ct["startOnBoot"] is True

    return _after_all(check)


@pulumi.runtime.test
def test_sizes_follow_the_topology():
    def check():
        cts = MOCKS.containers()
        for role, guest in STACK.guests.items():
            ct = cts[guest.name]
            assert ct["cpu"] == {"cores": guest.cores}
            assert ct["memory"]["dedicated"] == guest.memory_mb
            assert ct["disk"] == {"datastoreId": "local-lvm", "size": guest.disk_gb}, (
                role
            )

    return _after_all(check)


def test_secrets_are_generated_not_configured():
    assert set(STACK.secrets) == {
        "catalog_to_instances_token",
        "instances_db_password",
        "instances_to_catalog_token",
        "jwt_signing_key",
        "jwt_verifying_key",
        "db_password",
        "django_secret_key",
        "grafana_admin_password",
        "loadtest_owner_password",
        "redis_password",
        "mongo_admin_password",
        "mongo_instances_password",
        "mongo_exporter_password",
        "mongo_keyfile",
    }
