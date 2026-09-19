# zec-fleet

Find, audit, and repoint a fleet of Antminer Z15 Pros hosted by someone else, so every machine mines to **your** 2Miners address. Built on [pyasic](https://github.com/UpstreamData/pyasic).

It talks to each miner the way its own web page does: port 80 with digest auth, which works on stock Bitmain firmware where SSH is turned off. It also reads the read-only status API on port 4028. Run it from any machine that can reach the miners' network, for example over the lessor's VPN or a jump box on their LAN.

```sh
uv tool install "git+https://github.com/skeptrunedev/zec#subdirectory=fleet"
```

## Commands

```sh
# What's out there: model, firmware, serial, hashrate, and all three pool slots
zec-fleet scan 10.0.0.0/24

# Anything that costs you money: wrong model, non-stock firmware (dev fees),
# a pool slot or active connection mining for someone else, hashrate below 815 kSol/s.
# Exits 1 if anything's wrong.
zec-fleet audit 10.0.0.0/24 --address t1YourAddress

# Point all three pool slots at your address. Dry run unless you pass --apply.
zec-fleet set-pools 10.0.0.0/24 --address t1YourAddress
zec-fleet set-pools 10.0.0.0/24 --address t1YourAddress --apply
```

Targets are subnets (`10.0.0.0/24`) or ranges (`10.0.1.1-130`). Use `--password` if the web password isn't `root`, and `--json` on `scan` and `audit` for machine-readable output.

`set-pools` changes **only** the pools. It reads each miner's current fan, frequency and mode settings and sends them back unchanged, then reads the config back to confirm the change took. Each worker name is `ADDRESS.SERIAL`, so the pool shows you every machine by its serial number.

- **Pool slots:** all three point at 2Miners, primary region first (`--region us|eu|asia`).
- **Encryption:** `--ssl` makes slot 1 encrypted (port 11010) and keeps plain TCP in slots 2–3, so firmware without SSL support still falls back to your own pool. Try it on one machine first, then run `scan`: if the active pool shows the TCP URL, that firmware doesn't support SSL.

## First week with a new fleet

1. **Scan and audit before changing anything**, and save the output. It records what the lessor set up: firmware, serial numbers, and whose pools were configured.
2. **Trial 5–10 machines.** Run `set-pools <their IPs> --apply`, then open `https://zec.skeptrune.com/watch?address=t1YourAddress&machines=10`.
3. **Wait 48–72 hours.** Each machine's pool-side average should hold at or above about 815 kSol/s (spec is 840 ±3%). Payouts should land in your wallet every 2 hours once you're past the 0.1 ZEC minimum.
4. **Move the rest,** then run `audit` daily. A foreign pool slot or active connection that shows up later means someone changed it back.

Pool-side numbers are the only ones to trust: modified firmware can report a full hashrate while quietly sending part of the work elsewhere.

## Development

```sh
uv sync && uv run pytest
```
