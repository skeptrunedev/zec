import pytest

from zec_fleet.plan import (
    MinerReport,
    PoolSlot,
    audit,
    build_payload,
    desired_pools,
    is_t_address,
    pools_match,
    rig_id,
)

ADDR = "t1WAzmV9m7hvfSDxViP5c7aRkUMFFCMqmUN"


def test_address_validation():
    assert is_t_address(ADDR)
    assert not is_t_address("zs1abc")
    assert not is_t_address(ADDR[:-1])


def test_rig_id_prefers_serial_and_sanitizes():
    assert rig_id("JYZZB4ABCD123", "10.0.0.5") == "JYZZB4ABCD123"
    assert rig_id(None, "10.0.0.5") == "ip-10-0-0-5"
    assert rig_id("  ", "10.0.0.5") == "ip-10-0-0-5"
    assert rig_id("A B/C", "1.1.1.1") == "A-B-C"
    assert len(rig_id("X" * 50, "1.1.1.1")) == 32


def test_desired_pools_are_all_ours():
    pools = desired_pools(ADDR, "SN1")
    assert [p["url"] for p in pools] == [
        "stratum+tcp://us-zec.2miners.com:1010",
        "stratum+tcp://zec.2miners.com:1010",
        "stratum+tcp://asia-zec.2miners.com:1010",
    ]
    assert all(p["user"] == f"{ADDR}.SN1" and p["pass"] == "x" for p in pools)


def test_ssl_slot_first_with_tcp_fallbacks():
    pools = desired_pools(ADDR, "SN1", region="eu", ssl=True)
    assert [p["url"] for p in pools] == [
        "stratum+ssl://zec.2miners.com:11010",
        "stratum+tcp://zec.2miners.com:1010",
        "stratum+tcp://us-zec.2miners.com:1010",
    ]


def test_bad_region_rejected():
    with pytest.raises(ValueError):
        desired_pools(ADDR, "SN1", region="mars")


def test_payload_keeps_tuning_and_replaces_pools():
    current = {
        "bitmain-fan-ctrl": False,
        "bitmain-fan-pwm": "100",
        "freq-level": "95",
        "miner-mode": 0,
        "api-listen": True,
        "pools": [{"url": "stratum+tcp://evil:3333", "user": "them.1", "pass": "x"}],
    }
    pools = desired_pools(ADDR, "SN1")
    payload = build_payload(current, pools)
    assert payload == {
        "bitmain-fan-ctrl": False,
        "bitmain-fan-pwm": "100",
        "freq-level": "95",
        "miner-mode": 0,
        "pools": pools,
    }
    assert not pools_match(current, pools)
    assert pools_match({"pools": pools}, pools)


def good_report(**overrides):
    base = dict(
        ip="10.0.0.5",
        model="Z15 Pro",
        firmware="Stock",
        hashrate_ksol=838,
        slots=[PoolSlot(p["url"], p["user"]) for p in desired_pools(ADDR, "SN1")],
        active_user=f"{ADDR}.SN1",
    )
    base.update(overrides)
    return MinerReport(**base)


def test_clean_miner_passes():
    assert audit(good_report(), ADDR, 815) == []


def test_audit_flags_each_problem():
    report = good_report(
        model="Z15",
        firmware="VNish",
        hashrate_ksol=700,
        slots=[PoolSlot("stratum+tcp://us-zec.2miners.com:1010", f"{ADDR}.SN1"), PoolSlot("stratum+tcp://evil:3333", "them.1"), PoolSlot("", "")],
        active_user="them.1",
    )
    problems = audit(report, ADDR, 815)
    assert len(problems) == 5
    assert any("slot 2" in p for p in problems)
    assert not any("slot 3" in p for p in problems)  # empty slots can't redirect anything


def test_address_prefix_is_not_enough():
    # Someone else's worker on an address that merely starts like yours.
    report = good_report(active_user=ADDR + "X.1")
    assert audit(report, ADDR, 815) == ["currently mining for someone else: " + ADDR + "X.1"]


def test_unreachable():
    assert audit(MinerReport(ip="10.0.0.9", error="timeout"), ADDR, 815) == ["unreachable: timeout"]
