"""Pure fleet logic: pool plans, config payloads, and audit rules.

Nothing here touches the network, so it is all unit-tested. The CLI feeds it
what it reads from each miner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 2Miners ZEC endpoints, from https://zec.2miners.com/help (checked 2026-09-19).
TWO_MINERS_HOSTS = {
    "us": "us-zec.2miners.com",
    "eu": "zec.2miners.com",
    "asia": "asia-zec.2miners.com",
}
TCP_PORT = 1010
SSL_PORT = 11010

# Transparent Zcash addresses: t1 (P2PKH) or t3 (P2SH), base58, 35 chars.
T_ADDRESS = re.compile(r"^t[13][1-9A-HJ-NP-Za-km-z]{33}$")

# 2Miners rig IDs: up to 32 of letters, digits, "-" and "_".
RIG_ID_MAX = 32

# Keys the Antminer web UI sends back alongside "pools" when you press Save.
# We resend the miner's current values untouched so only the pools change;
# a full pyasic config would reset fan, frequency and mode to its defaults.
PRESERVED_CONF_KEYS = (
    "bitmain-fan-ctrl",
    "bitmain-fan-pwm",
    "bitmain-fan-pwn",  # misspelled key some firmware builds use
    "freq-level",
    "miner-mode",
)

Z15_PRO_MODEL = "Z15 Pro"
STOCK_FIRMWARE = "Stock"


def is_t_address(address: str) -> bool:
    return bool(T_ADDRESS.match(address))


def rig_id(serial: str | None, ip: str) -> str:
    """Worker suffix for 2Miners: the serial number when the miner reports one."""
    raw = serial.strip() if serial and serial.strip() else f"ip-{ip.replace('.', '-')}"
    return re.sub(r"[^A-Za-z0-9_-]", "-", raw)[:RIG_ID_MAX]


def desired_pools(address: str, rig: str, region: str = "us", ssl: bool = False) -> list[dict]:
    """Three pool slots, all yours: the primary region first, then the others.

    With ssl, slot 1 is the encrypted endpoint and slots 2-3 are plain TCP, so a
    firmware build without SSL support still fails over to your own pool.
    """
    if region not in TWO_MINERS_HOSTS:
        raise ValueError(f"region must be one of {', '.join(TWO_MINERS_HOSTS)}")
    order = [region, *(r for r in TWO_MINERS_HOSTS if r != region)]
    urls = [f"stratum+tcp://{TWO_MINERS_HOSTS[r]}:{TCP_PORT}" for r in order]
    if ssl:
        urls = [f"stratum+ssl://{TWO_MINERS_HOSTS[region]}:{SSL_PORT}", *urls[:2]]
    user = f"{address}.{rig}"
    return [{"url": url, "user": user, "pass": "x"} for url in urls]


def build_payload(current_conf: dict, pools: list[dict]) -> dict:
    """What to POST to set_miner_conf: current settings, new pools."""
    payload = {k: current_conf[k] for k in PRESERVED_CONF_KEYS if k in current_conf}
    payload["pools"] = pools
    return payload


def pools_match(conf: dict, pools: list[dict]) -> bool:
    got = [(p.get("url", ""), p.get("user", "")) for p in conf.get("pools", [])]
    want = [(p["url"], p["user"]) for p in pools]
    return got[: len(want)] == want


def is_ours(user: str | None, address: str) -> bool:
    return bool(user) and (user == address or user.startswith(address + "."))


@dataclass
class PoolSlot:
    url: str
    user: str


@dataclass
class MinerReport:
    ip: str
    model: str | None = None
    firmware: str | None = None
    fw_ver: str | None = None
    serial: str | None = None
    hashrate_ksol: float | None = None
    # From the web config: what each slot is set to.
    slots: list[PoolSlot] = field(default_factory=list)
    # From the RPC pool list: the user the miner is actually mining for right now.
    active_user: str | None = None
    error: str | None = None


def audit(report: MinerReport, address: str, min_ksol: float) -> list[str]:
    """Problems that cost you money or mean the lessor can redirect hashrate."""
    if report.error:
        return [f"unreachable: {report.error}"]

    problems = []
    if report.model != Z15_PRO_MODEL:
        problems.append(f"model is {report.model or 'unknown'}, not {Z15_PRO_MODEL}")
    if report.firmware != STOCK_FIRMWARE:
        problems.append(f"{report.firmware or 'unknown'} firmware, not stock: may take a dev fee")
    for i, slot in enumerate(report.slots, start=1):
        if slot.url and not is_ours(slot.user, address):
            problems.append(f"pool slot {i} mines for someone else: {slot.url} {slot.user}")
    if report.active_user is not None and not is_ours(report.active_user, address):
        problems.append(f"currently mining for someone else: {report.active_user}")
    if report.hashrate_ksol is not None and report.hashrate_ksol < min_ksol:
        problems.append(f"hashrate {report.hashrate_ksol:.0f} kSol/s is below {min_ksol:.0f}")
    return problems
