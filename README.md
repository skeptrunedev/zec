# zec

Live Zcash mining profitability calculator for the Antminer Z15 Pro, served at https://zec.skeptrune.com.

- `public/index.html` is the page; `public/calc.js` holds the math (shared with tests).
- `src/index.ts` is a Cloudflare Worker exposing `/api/stats` (Blockchair network hashrate + CoinGecko price, cached 5 min).
- `public/watch.html` is the fleet monitor (`/watch`): pool-side hashrate per machine from 2Miners via `/api/pool/:address`.
- `fleet/` is `zec-fleet`, a CLI to scan, audit, and repoint hosted Z15 Pros. See [fleet/README.md](fleet/README.md).
- Every input is editable: hashrate, power, units, $/kWh, pool fee, rental/hosting $/day, hardware cost, ZEC price, network hashrate.

```sh
npm install
npm run dev     # local worker
npm test        # calc tests
```

Pushes to `main` deploy via GitHub Actions.

MIT licensed.
