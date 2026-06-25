import { fetchStockPricesBatch } from "@/api/assets";
import { CASH_TICKER } from "@/constants/assets";
import { RebalancingAnalysis } from "@/api/rebalancing";
import type { ExecutionAction } from "./useRebalancingExecution";
import { getActionableItems } from "./useRebalancingExecution";
import { toast } from "@/utils/toast";

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
  analysis: RebalancingAnalysis,
) {
  async function loadAllPrices() {
    const tickerMarketMap = new Map<string, string>();
    getActionableItems(analysis).forEach((i) => {
      if (i.ticker !== CASH_TICKER) tickerMarketMap.set(i.ticker, i.market);
    });
    analysis.untracked_holdings.forEach((h) => tickerMarketMap.set(h.ticker, h.market));
    if (tickerMarketMap.size === 0) return;

    const entries = Array.from(tickerMarketMap.entries());

    // 캐시 미스 항목만 배치로 fetch (N개 병렬 → 단 1회 호출)
    const toFetch = entries
      .filter(([ticker]) => !getCached(ticker))
      .map(([ticker, market]) => ({ ticker, market }));

    if (toFetch.length > 0) {
      dispatch({ type: "PRICES_START", total: toFetch.length });
      try {
        const batchResult = await fetchStockPricesBatch(toFetch);
        for (const { ticker } of toFetch) {
          const entry = batchResult[ticker];
          if (entry) {
            _priceCache.set(ticker, { ...entry, fetchedAt: Date.now() });
          }
        }
        const failedCount = toFetch.filter(({ ticker }) => !batchResult[ticker]?.price_krw && !batchResult[ticker]?.price_usd).length;
        if (failedCount > 0 && failedCount < toFetch.length) {
          toast(`${failedCount}개 종목 현재가 조회 실패`, "error");
        }
      } catch {
        toast("현재가 일괄 조회 실패 — 잠시 후 다시 시도하세요", "error");
      }
      dispatch({ type: "PRICES_PROGRESS", loaded: toFetch.length });
    }

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
