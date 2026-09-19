"""zec-fleet: find, audit, and repoint a hosted fleet of Antminer Z15 Pros.

Talks to each miner the same way its web page does (port 80, digest auth) plus
the read-only status API on port 4028, via pyasic.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict

import pyasic
from pyasic import settings
from pyasic.device.algorithm.hashrate.unit.equihash import EquihashUnit
from pyasic.network import MinerNetwork

from zec_fleet.plan import (
    TWO_MINERS_HOSTS,
    MinerReport,
    PoolSlot,
    audit,
    build_payload,
    desired_pools,
    is_t_address,
    pools_match,
    rig_id,
)


def network(targets: list[str]) -> MinerNetwork:
    hosts = []
    for t in targets:
        net = MinerNetwork.from_subnet(t) if "/" in t else MinerNetwork.from_address(t)
        hosts.extend(net.hosts)
    return MinerNetwork(sorted(set(hosts)))


async def read(miner) -> tuple[MinerReport, dict]:
    ip = str(miner.ip)
    try:
        data = await miner.get_data()
        conf = await miner.web.get_miner_conf() if hasattr(miner.web, "get_miner_conf") else {}
    except Exception as e:  # one bad miner shouldn't stop a fleet-wide pass
        return MinerReport(ip=ip, error=str(e) or type(e).__name__), {}

    hashrate = data.hashrate
    active = next((p for p in data.pools if p.active), None)
    report = MinerReport(
        ip=ip,
        model=data.model or None,
        firmware=data.firmware or None,
        fw_ver=data.fw_ver,
        serial=data.serial_number,
        hashrate_ksol=float(hashrate.into(EquihashUnit.KH).rate) if hashrate is not None else None,
        slots=[PoolSlot(p.get("url", ""), p.get("user", "")) for p in conf.get("pools", [])],
        active_user=active.user if active else None,
    )
    return report, conf


async def gather_limited(coros, limit: int):
    sem = asyncio.Semaphore(limit)

    async def run(c):
        async with sem:
            return await c

    return await asyncio.gather(*(run(c) for c in coros))


async def discover(args) -> list:
    miners = await network(args.targets).scan()
    print(f"found {len(miners)} miner(s)", file=sys.stderr)
    return sorted(miners, key=lambda m: tuple(int(o) for o in str(m.ip).split(".")))


def fmt_ksol(v: float | None) -> str:
    return "—" if v is None else f"{v:,.0f}"


async def cmd_scan(args) -> int:
    miners = await discover(args)
    reports = [r for r, _ in await gather_limited([read(m) for m in miners], args.concurrency)]
    if args.json:
        print(json.dumps([asdict(r) for r in reports], indent=2))
        return 0
    print(f"{'IP':<16}{'MODEL':<10}{'FIRMWARE':<10}{'SERIAL':<20}{'kSol/s':>8}  POOL SLOTS")
    for r in reports:
        if r.error:
            print(f"{r.ip:<16}unreachable: {r.error}")
            continue
        slots = " | ".join(f"{s.url} {s.user}" for s in r.slots if s.url) or "none"
        print(f"{r.ip:<16}{r.model or '?':<10}{r.firmware or '?':<10}{r.serial or '?':<20}{fmt_ksol(r.hashrate_ksol):>8}  {slots}")
    return 0


async def cmd_audit(args) -> int:
    miners = await discover(args)
    reports = [r for r, _ in await gather_limited([read(m) for m in miners], args.concurrency)]
    results = [(r, audit(r, args.address, args.min)) for r in reports]
    bad = [(r, p) for r, p in results if p]
    total = sum(r.hashrate_ksol or 0 for r in reports)

    if args.json:
        print(json.dumps([{"report": asdict(r), "problems": p} for r, p in results], indent=2))
    else:
        for r, problems in bad:
            print(f"{r.ip} ({r.serial or 'no serial'})")
            for p in problems:
                print(f"  - {p}")
        print(
            f"\n{len(reports)} miners, {len(reports) - len(bad)} clean, {len(bad)} with problems. "
            f"Miner-reported total {total / 1000:,.1f} MSol/s (check it against the pool-side number)."
        )
    return 1 if bad else 0


async def set_one(miner, args) -> tuple[str, str]:
    report, conf = await read(miner)
    if report.error:
        return report.ip, f"skipped, unreachable: {report.error}"
    if not conf.get("pools"):
        return report.ip, "skipped, couldn't read its pool config"
    pools = desired_pools(args.address, rig_id(report.serial, report.ip), args.region, args.ssl)
    if pools_match(conf, pools):
        return report.ip, "already set"
    if not args.apply:
        return report.ip, "would set: " + ", ".join(f"{p['url']} {p['user']}" for p in pools)

    await miner.web.set_miner_conf(build_payload(conf, pools))
    # Read it back: the miner's word, not the POST response, decides success.
    for _ in range(10):
        await asyncio.sleep(2)
        if pools_match(await miner.web.get_miner_conf(), pools):
            return report.ip, "set ✓"
    return report.ip, "FAILED: pools didn't change, check this one by hand"


async def cmd_set_pools(args) -> int:
    miners = await discover(args)
    results = await gather_limited([set_one(m, args) for m in miners], args.concurrency)
    for ip, outcome in results:
        print(f"{ip:<16}{outcome}")
    if not args.apply:
        print("\ndry run: nothing changed. Re-run with --apply to write these pools.", file=sys.stderr)
    return 1 if any("FAILED" in o or "skipped" in o for _, o in results) else 0


def address_arg(value: str) -> str:
    if not is_t_address(value):
        raise argparse.ArgumentTypeError("must be a transparent Zcash address (t1… or t3…)")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zec-fleet", description=__doc__)
    parser.add_argument("--password", default="root", help="miner web password (default: root)")
    parser.add_argument("--concurrency", type=int, default=20, help="miners handled at once (default: 20)")
    sub = parser.add_subparsers(dest="command", required=True)

    def targets(p):
        p.add_argument("targets", nargs="+", help='subnets or ranges, e.g. 10.0.0.0/24 or "10.0.1.1-130"')

    p = sub.add_parser("scan", help="list every miner: model, firmware, serial, hashrate, pool slots")
    targets(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_scan)

    p = sub.add_parser("audit", help="flag wrong models, non-stock firmware, foreign pool slots, low hashrate")
    targets(p)
    p.add_argument("--address", type=address_arg, required=True, help="your 2Miners payout address")
    p.add_argument("--min", type=float, default=815, help="minimum kSol/s per machine (default: 815)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_audit)

    p = sub.add_parser("set-pools", help="point all three pool slots at your 2Miners address (dry run by default)")
    targets(p)
    p.add_argument("--address", type=address_arg, required=True, help="your 2Miners payout address")
    p.add_argument("--region", choices=list(TWO_MINERS_HOSTS), default="us", help="primary 2Miners region (default: us)")
    p.add_argument("--ssl", action="store_true", help="encrypted slot 1 (port 11010), plain TCP fallbacks")
    p.add_argument("--apply", action="store_true", help="actually write the new pools")
    p.set_defaults(run=cmd_set_pools)

    args = parser.parse_args(argv)
    settings.update("default_antminer_web_password", args.password)
    return asyncio.run(args.run(args))


if __name__ == "__main__":
    sys.exit(main())
