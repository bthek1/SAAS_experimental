import ipaddress

import pytest

from saas_loadtest import topology
from saas_loadtest.topology import Network, build

NETWORK = Network(cidr="192.168.2.0/24", gateway="192.168.2.1")


def test_four_guests_with_fixed_ids():
    guests = build(NETWORK)
    assert {role: g.vmid for role, g in guests.items()} == {
        "app": 241,
        "db": 242,
        "monitor": 243,
        "loadgen": 244,
    }
    assert [g.name for g in guests.values()] == [
        "saas-app",
        "saas-db",
        "saas-monitor",
        "saas-loadgen",
    ]


def test_ip_is_the_id_as_last_octet():
    for guest in build(NETWORK).values():
        assert guest.ip == f"192.168.2.{guest.vmid}"
        assert guest.address == f"192.168.2.{guest.vmid}/24"
        assert ipaddress.ip_address(guest.ip).is_private


@pytest.mark.parametrize("vmid", [220, 226, 240])
def test_kubernates_project_ids_are_refused(vmid):
    with pytest.raises(ValueError, match="kubernates_project"):
        topology.check_vmid(vmid)


@pytest.mark.parametrize("vmid", [100, 200, 219, 250])
def test_ids_outside_the_range_are_refused(vmid):
    with pytest.raises(ValueError, match="outside this repo's range"):
        topology.check_vmid(vmid)


def test_every_id_is_in_range_and_unique():
    ids = list(topology.GUEST_IDS.values())
    assert len(ids) == len(set(ids))
    assert all(vmid in topology.ID_RANGE for vmid in ids)
    assert not set(ids) & set(topology.RESERVED)


def test_a_public_network_is_refused():
    with pytest.raises(ValueError, match="not a private network"):
        build(Network(cidr="8.8.8.0/24", gateway="8.8.8.1"))


def test_an_id_outside_a_small_network_is_refused():
    with pytest.raises(ValueError, match="not a host in"):
        build(Network(cidr="192.168.2.0/25", gateway="192.168.2.1"))


def test_sizes_override_per_role():
    guests = build(NETWORK, {"app": {"cores": 4}})
    assert guests["app"].cores == 4
    assert guests["app"].memory_mb == topology.DEFAULT_SIZES["app"]["memoryMb"]
    assert guests["db"].cores == topology.DEFAULT_SIZES["db"]["cores"]


def test_sizes_for_an_unknown_role_are_refused():
    with pytest.raises(ValueError, match="unknown roles"):
        build(NETWORK, {"web": {"cores": 1}})


def test_default_memory_fits_the_budget():
    # The host had ~24 GB available on 2026-11-02; keep this deploy small.
    total = sum(size["memoryMb"] for size in topology.DEFAULT_SIZES.values())
    assert total <= 6 * 1024
