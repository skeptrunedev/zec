# zec

Live Zcash mining profitability calculator for the Antminer Z15 Pro, served at https://zec.skeptrune.com.

- `public/index.html` is the page; `public/calc.js` holds the math (shared with tests).
- `src/index.ts` is a Cloudflare Worker exposing `/api/stats` (Blockchair network hashrate + CoinGecko price, cached 5 min).
- Every input is editable: hashrate, power, units, $/kWh, pool fee, rental/hosting $/day, hardware cost, ZEC price, network hashrate.

```sh
npm install
npm run dev     # local worker
npm test        # calc tests
```

Pushes to `main` deploy via GitHub Actions.
