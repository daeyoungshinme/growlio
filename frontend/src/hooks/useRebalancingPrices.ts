import { fetchStockPrice } from "../api/assets";
import { RebalancingAnalysis } from "../api/rebalancing";
import type { ExecutionAction } from "./useRebalancingExecution";
import { getActionableItems } from "./useRebalancingExecution";

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
    dispatch({ type: "PRICES_START", total: entries.length });

    let loaded = 0;
    const priceResults = await Promise.allSettled(
      entries.map(async ([ticker, market]) => {
        const result = await fetchStockPrice(ticker, market);
        dispatch({ type: "PRICES_PROGRESS", loaded: ++loaded });
        return result;
      })
    );

    const newKrw: Record<string, number> = {};
    const newUsd: Record<string, number> = {};
    let latestUsdRate: number | null = null;
    priceResults.forEach((result, idx) => {
      const [ticker] = entries[idx];
      if (result.status === "fulfilled") {
        const { price_krw, price_usd, usd_rate } = result.value;
        if (price_krw != null) newKrw[ticker] = price_krw;
        if (price_usd != null) newUsd[ticker] = price_usd;
        if (usd_rate != null) latestUsdRate = usd_rate;
      }
    });
    dispatch({ type: "PRICES_DONE", krw: newKrw, usd: newUsd, usdRate: latestUsdRate });
  }

  return { loadAllPrices };
}
