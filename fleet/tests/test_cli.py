"""The miner-facing flow, against a stand-in miner built from real pyasic types."""

import asyncio
from types import SimpleNamespace

from pyasic.data import MinerData
from pyasic.data.device import DeviceInfo
from pyasic.data.pools import PoolMetrics, PoolUrl
from pyasic.device.algorithm import MinerAlgo
from pyasic.device.algorithm.hashrate.equihash import EquihashHashRate
from pyasic.device.algorithm.hashrate.unit.equihash import EquihashUnit
from pyasic.device.firmware import MinerFirmware
from pyasic.device.makes import MinerMake
from pyasic.device.models import MinerModel

from zec_fleet import cli
from zec_fleet.plan import audit, desired_pools

ADDR = "t1WAzmV9m7hvfSDxViP5c7aRkUMFFCMqmUN"
THEIRS = {"url": "stratum+tcp://lessor.example:3333", "user": "lessor.rig7", "pass": "x"}


class FakeWeb:
    def __init__(self, conf, accept_writes=True):
        self.conf = conf
        self.accept_writes = accept_writes
        self.posted = None

    async def get_miner_conf(self):
        return self.conf

    async def set_miner_conf(self, payload):
        self.posted = payload
        if self.accept_writes:
            self.conf = {**self.conf, **payload}
        return {"stats": "success"}


class FakeMiner:
    def __init__(self, conf, accept_writes=True, firmware=MinerFirmware.STOCK):
        self.ip = "10.0.0.7"
        self.web = FakeWeb(conf, accept_writes)
        self.firmware = firmware

    async def get_data(self):
        active_user = self.web.conf["pools"][0]["user"]
        return MinerData(
            ip=self.ip,
            device_info=DeviceInfo(
                make=MinerMake.ANTMINER,
                model=MinerModel.ANTMINER.Z15Pro,
                firmware=self.firmware,
                algo=MinerAlgo.EQUIHASH,
            ),
            serial_number="JYZZB4TEST001",
            raw_hashrate=EquihashHashRate(rate=0.836, unit=EquihashUnit.MH),
            pools=[
                PoolMetrics(url=PoolUrl.from_str(self.web.conf["pools"][0]["url"]), user=active_user, active=True, alive=True, index=0)
            ],
        )


def tuned_conf():
    return {"bitmain-fan-ctrl": False, "bitmain-fan-pwm": "100", "freq-level": "95", "miner-mode": 0, "pools": [THEIRS]}


def args(**kw):
    return SimpleNamespace(**{"address": ADDR, "region": "us", "ssl": False, "apply": False, **kw})


def run(coro):
    return asyncio.run(coro)


def test_read_converts_pyasic_data():
    report, _ = run(cli.read(FakeMiner(tuned_conf())))
    assert report.model == "Z15 Pro"
    assert report.firmware == "Stock"
    assert report.serial == "JYZZB4TEST001"
    assert round(report.hashrate_ksol) == 836
    assert report.active_user == "lessor.rig7"
    problems = audit(report, ADDR, 815)
    assert problems == [
        "pool slot 1 mines for someone else: stratum+tcp://lessor.example:3333 lessor.rig7",
        "currently mining for someone else: lessor.rig7",
    ]


def test_non_stock_firmware_is_flagged():
    report, _ = run(cli.read(FakeMiner(tuned_conf(), firmware=MinerFirmware.VNISH)))
    assert any("VNish firmware" in p for p in audit(report, ADDR, 815))


def test_dry_run_changes_nothing():
    miner = FakeMiner(tuned_conf())
    ip, outcome = run(cli.set_one(miner, args()))
    assert outcome.startswith("would set: stratum+tcp://us-zec.2miners.com:1010 " + ADDR + ".JYZZB4TEST001")
    assert miner.web.posted is None


def test_apply_writes_only_pools_and_verifies(monkeypatch):
    async def no_sleep(_):
        pass

    monkeypatch.setattr(cli.asyncio, "sleep", no_sleep)
    miner = FakeMiner(tuned_conf())
    ip, outcome = run(cli.set_one(miner, args(apply=True)))
    assert outcome == "set ✓"
    want = desired_pools(ADDR, "JYZZB4TEST001")
    assert miner.web.posted == {"bitmain-fan-ctrl": False, "bitmain-fan-pwm": "100", "freq-level": "95", "miner-mode": 0, "pools": want}
    # Second pass sees it's done and doesn't write again.
    miner.web.posted = None
    assert run(cli.set_one(miner, args(apply=True)))[1] == "already set"
    assert miner.web.posted is None


def test_apply_reports_failure_when_miner_ignores_write(monkeypatch):
    async def no_sleep(_):
        pass

    monkeypatch.setattr(cli.asyncio, "sleep", no_sleep)
    miner = FakeMiner(tuned_conf(), accept_writes=False)
    assert run(cli.set_one(miner, args(apply=True)))[1].startswith("FAILED")


def test_unreachable_miner_is_reported_not_raised():
    class Broken(FakeMiner):
        async def get_data(self):
            raise TimeoutError("timed out")

    report, conf = run(cli.read(Broken(tuned_conf())))
    assert report.error == "timed out" and conf == {}
    assert run(cli.set_one(Broken(tuned_conf()), args()))[1] == "skipped, unreachable: timed out"
