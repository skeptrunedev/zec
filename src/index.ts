// Live Zcash network stats for the calculator page.
//
// Network hashrate comes from Blockchair (24h average, sol/s). Price comes from
// CoinGecko, with Blockchair's own market price as the second source. ViaBTC's
// published payout per kSol/s is fetched as an independent cross-check of the
// page's math. All are fetched server-side so the page has one same-origin,
// cached endpoint.

interface Env {
  ASSETS: Fetcher;
}

export interface Stats {
  priceUsd: number;
  priceSource: "coingecko" | "blockchair";
  networkSolPerSec: number;
  difficulty: number;
  height: number;
  // ViaBTC's expected ZEC per kSol/s per day, after its pool fee. Null if unavailable.
  poolZecPerKsolDay: number | null;
  fetchedAt: string;
}

const CACHE_SECONDS = 300;

interface BlockchairStats {
  data: {
    best_block_height: number;
    difficulty: number;
    hashrate_24h: string;
    market_price_usd: number;
  };
}

interface ViaBtcState {
  data?: { unit_output?: string; hash_unit?: string };
}

interface CoinGeckoPrice {
  zcash?: { usd?: number };
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { accept: "application/json", "user-agent": "zec.skeptrune.com" } });
  if (!res.ok) throw new Error(`${new URL(url).host} returned ${res.status}`);
  return res.json<T>();
}

async function loadStats(): Promise<Stats> {
  const [chain, gecko, viabtc] = await Promise.allSettled([
    getJson<BlockchairStats>("https://api.blockchair.com/zcash/stats"),
    getJson<CoinGeckoPrice>("https://api.coingecko.com/api/v3/simple/price?ids=zcash&vs_currencies=usd"),
    getJson<ViaBtcState>("https://www.viabtc.com/res/pool/ZEC/state"),
  ]);
  if (chain.status === "rejected") throw chain.reason;

  const d = chain.value.data;
  const networkSolPerSec = Number(d.hashrate_24h);
  if (!(networkSolPerSec > 0)) throw new Error("blockchair returned no network hashrate");

  const geckoPrice = gecko.status === "fulfilled" ? gecko.value.zcash?.usd : undefined;
  const priceUsd = geckoPrice ?? d.market_price_usd;
  if (!(priceUsd > 0)) throw new Error("no ZEC price available");

  const via = viabtc.status === "fulfilled" ? viabtc.value.data : undefined;
  const poolZecPerKsolDay = via?.hash_unit === "KSol/s" ? Number(via.unit_output) : NaN;

  return {
    priceUsd,
    priceSource: geckoPrice ? "coingecko" : "blockchair",
    networkSolPerSec,
    difficulty: d.difficulty,
    height: d.best_block_height,
    poolZecPerKsolDay: poolZecPerKsolDay > 0 ? poolZecPerKsolDay : null,
    fetchedAt: new Date().toISOString(),
  };
}

// 2Miners reports amounts in 1e-8 ZEC units and hashrates in sol/s.
const TWO_MINERS_UNITS_PER_ZEC = 1e8;
const POOL_CACHE_SECONDS = 60;
// Transparent Zcash addresses: t1 (P2PKH) or t3 (P2SH), base58, 35 chars.
const T_ADDRESS = /^t[13][1-9A-HJ-NP-Za-km-z]{33}$/;

interface TwoMinersAccount {
  currentHashrate: number;
  hashrate: number;
  workersOnline: number;
  workersOffline: number;
  updatedAt: number;
  "24hreward": number;
  stats: { balance: number; immature: number; paid: number; lastShare: number };
  workers: Record<string, { hr: number; hr2: number; offline: boolean; lastBeat: number }>;
  payments: { amount: number; timestamp: number; tx: string }[] | null;
}

export interface PoolAccount {
  pool: "2miners";
  address: string;
  currentSolPerSec: number;
  averageSolPerSec: number;
  workersOnline: number;
  workersOffline: number;
  reward24hZec: number;
  balanceZec: number;
  immatureZec: number;
  paidZec: number;
  lastShare: number;
  workers: { name: string; currentSolPerSec: number; averageSolPerSec: number; offline: boolean; lastBeat: number }[];
  payments: { zec: number; timestamp: number; tx: string }[];
  updatedAt: number;
}

async function loadPoolAccount(address: string): Promise<PoolAccount> {
  const a = await getJson<TwoMinersAccount>(`https://zec.2miners.com/api/accounts/${address}`);
  const zec = (units: number) => units / TWO_MINERS_UNITS_PER_ZEC;
  return {
    pool: "2miners",
    address,
    currentSolPerSec: a.currentHashrate,
    averageSolPerSec: a.hashrate,
    workersOnline: a.workersOnline,
    workersOffline: a.workersOffline,
    reward24hZec: zec(a["24hreward"]),
    balanceZec: zec(a.stats.balance),
    immatureZec: zec(a.stats.immature),
    paidZec: zec(a.stats.paid),
    lastShare: a.stats.lastShare,
    workers: Object.entries(a.workers ?? {})
      .map(([name, w]) => ({
        name,
        currentSolPerSec: w.hr,
        averageSolPerSec: w.hr2,
        offline: w.offline,
        lastBeat: w.lastBeat,
      }))
      .sort((x, y) => x.name.localeCompare(y.name, "en", { numeric: true })),
    payments: (a.payments ?? []).slice(0, 20).map((p) => ({ zec: zec(p.amount), timestamp: p.timestamp, tx: p.tx })),
    updatedAt: a.updatedAt,
  };
}

// Serves `load()` as JSON through the edge cache, keyed by the request URL.
async function cachedJson(
  request: Request,
  ctx: ExecutionContext,
  maxAge: number,
  load: () => Promise<unknown>,
): Promise<Response> {
  const cache = caches.default;
  const key = new Request(request.url);
  const hit = await cache.match(key);
  if (hit) return hit;

  try {
    const res = Response.json(await load(), {
      headers: { "cache-control": `public, max-age=${maxAge}` },
    });
    ctx.waitUntil(cache.put(key, res.clone()));
    return res;
  } catch (err) {
    return Response.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/api/stats") {
      return cachedJson(new Request(new URL("/api/stats", url)), ctx, CACHE_SECONDS, loadStats);
    }
    const pool = url.pathname.match(/^\/api\/pool\/([^/]+)$/);
    if (pool) {
      const address = pool[1];
      if (!T_ADDRESS.test(address)) {
        return Response.json({ error: "not a transparent Zcash address (t1… or t3…)" }, { status: 400 });
      }
      return cachedJson(new Request(new URL(`/api/pool/${address}`, url)), ctx, POOL_CACHE_SECONDS, () =>
        loadPoolAccount(address),
      );
    }
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
