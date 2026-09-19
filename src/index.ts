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

async function handleStats(request: Request, ctx: ExecutionContext): Promise<Response> {
  const cache = caches.default;
  const key = new Request(new URL("/api/stats", request.url).toString());
  const hit = await cache.match(key);
  if (hit) return hit;

  try {
    const res = Response.json(await loadStats(), {
      headers: { "cache-control": `public, max-age=${CACHE_SECONDS}` },
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
    if (url.pathname === "/api/stats") return handleStats(request, ctx);
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
