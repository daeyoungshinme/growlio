import { fetchStockPrice, fetchStockPricesBatch } from "@/api/assets";
import { CASH_TICKER } from "@/constants/assets";
import { RebalancingAnalysis } from "@/api/rebalancing";
import type { ExecutionAction } from "./useRebalancingExecution";
import { getActionableItems } from "./useRebalancingExecution";
import { toast } from "@/utils/toast";
import { getHttpStatus } from "@/utils/error";

// 백엔드 현재가 캐시(TTL_PRICE_CURRENT=900s)와 동기화하는 세션 캐시
const PRICE_CACHE_TTL_MS = 900_000;
interface PriceCacheEntry {
  price_krw: number | null;
  price_usd: number | null;
  usd_rate: number | null;
  fetchedAt: number;
}
const _priceCache = new Map<string, PriceCacheEntry>();

// 다른 소스가 전부 실패했을 때만 쓰는 최후 폴백용 — 티커를 보유한 KIS 연동 계좌 ID (있으면)
function findKisAccountId(analysis: RebalancingAnalysis, ticker: string): string | undefined {
  return analysis.ticker_account_map[ticker]?.find((a) => a.asset_type === "STOCK_KIS")?.account_id;
}

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
      .map(([ticker, market]) => ({
        ticker,
        market,
        account_id: findKisAccountId(analysis, ticker),
      }));

    if (toFetch.length > 0) {
      dispatch({ type: "PRICES_START", total: toFetch.length });
      try {
        const batchResult = await fetchStockPricesBatch(toFetch);
        for (const { ticker } of toFetch) {
          const entry = batchResult[ticker];
          if (entry && (entry.price_krw != null || entry.price_usd != null)) {
            _priceCache.set(ticker, { ...entry, fetchedAt: Date.now() });
          }
        }
        const failedCount = toFetch.filter(
          ({ ticker }) => !batchResult[ticker]?.price_krw && !batchResult[ticker]?.price_usd,
        ).length;
        if (failedCount > 0 && failedCount < toFetch.length) {
          toast(`${failedCount}개 종목 현재가 조회 실패`, "error");
        }
      } catch (e) {
        const status = getHttpStatus(e);
        toast(
          `현재가 일괄 조회 실패${status ? ` (${status})` : ""} — 잠시 후 다시 시도하세요`,
          "error",
        );
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

  async function retryPrice(ticker: string, market: string) {
    dispatch({ type: "PRICE_RETRY_START", ticker });
    try {
      const result = await fetchStockPrice(ticker, market, findKisAccountId(analysis, ticker));
      if (result.price_krw != null || result.price_usd != null) {
        _priceCache.set(ticker, { ...result, fetchedAt: Date.now() });
        dispatch({
          type: "PRICE_RETRY_DONE",
          ticker,
          krw: result.price_krw ?? undefined,
          usd: result.price_usd ?? undefined,
          usdRate: result.usd_rate,
        });
      } else {
        dispatch({ type: "PRICE_RETRY_ERROR", ticker });
        toast(`${ticker} 현재가 조회 실패`, "error");
      }
    } catch (e) {
      dispatch({ type: "PRICE_RETRY_ERROR", ticker });
      const status = getHttpStatus(e);
      toast(`${ticker} 현재가 조회 실패${status ? ` (${status})` : ""}`, "error");
    }
  }

  return { loadAllPrices, retryPrice };
}
