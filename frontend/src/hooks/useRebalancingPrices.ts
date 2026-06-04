import { fetchStockPrice } from "../api/assets";
import { RebalancingAnalysis } from "../api/rebalancing";
import type { ExecutionAction } from "./useRebalancingExecution";
import { getActionableItems } from "./useRebalancingExecution";

// 백엔드 현재가 캐시(TTL_PRICE_CURRENT=900s)와 동기화하는 세션 캐시
const PRICE_CACHE_TTL_MS = 900_000;
interface PriceCacheEntry {
  price_krw: number | null;
  price_usd: number | null;
  usd_rate: number | null;
  fetchedAt: number;
}
const _priceCache = new Map<string, PriceCacheEntry>();

function getCached(ticker: string): PriceCacheEntry | null {
  const entry = _priceCache.get(ticker);
  if (!entry) return null;
  if (Date.now() - entry.fetchedAt > PRICE_CACHE_TTL_MS) {
    _priceCache.delete(ticker);
    return null;
  }
  return entry;
}

export function useRebalancingPrices(
  dispatch: React.Dispatch<ExecutionAction>,
  analysis: RebalancingAnalysis
) {
  async function loadAllPrices() {
    const tickerMarketMap = new Map<string, string>();
    getActionableItems(analysis).forEach((i) => {
      if (i.ticker !== "CASH") tickerMarketMap.set(i.ticker, i.market);
    });
    analysis.untracked_holdings.forEach((h) => tickerMarketMap.set(h.ticker, h.market));
    if (tickerMarketMap.size === 0) return;

    const entries = Array.from(tickerMarketMap.entries());

    // 캐시 히트 항목은 즉시 반영, 미스 항목만 fetch
    const toFetch = entries.filter(([ticker]) => !getCached(ticker));

    if (toFetch.length > 0) dispatch({ type: "PRICES_START", total: toFetch.length });

    let loaded = 0;
    await Promise.allSettled(
      toFetch.map(async ([ticker, market]) => {
        const result = await fetchStockPrice(ticker, market);
        _priceCache.set(ticker, { ...result, fetchedAt: Date.now() });
        dispatch({ type: "PRICES_PROGRESS", loaded: ++loaded });
      })
    );

    // 캐시(기존+신규)에서 최종 가격 맵 구성
    const newKrw: Record<string, number> = {};
    const newUsd: Record<string, number> = {};
    let latestUsdRate: number | null = null;
    for (const [ticker] of entries) {
      const hit = getCached(ticker);
      if (!hit) continue;
      if (hit.price_krw != null) newKrw[ticker] = hit.price_krw;
      if (hit.price_usd != null) newUsd[ticker] = hit.price_usd;
      if (hit.usd_rate != null) latestUsdRate = hit.usd_rate;
    }

    dispatch({ type: "PRICES_DONE", krw: newKrw, usd: newUsd, usdRate: latestUsdRate });
  }

  return { loadAllPrices };
}
