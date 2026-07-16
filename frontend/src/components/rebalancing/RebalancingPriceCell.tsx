import { RefreshCw } from "lucide-react";
import { fmtKrwPrice } from "@/utils/format";
import { isOverseasMarket } from "@/hooks/useRebalancingExecution";
import type { PriceLoadState } from "@/hooks/useRebalancingExecution";

export interface PriceCellProps {
  ticker: string;
  market: string;
  large?: boolean;
  priceState: PriceLoadState;
  livePricesKrw: Record<string, number>;
  livePricesUsd: Record<string, number>;
  priceRetrying?: Set<string>;
  onRetryPrice?: (ticker: string, market: string) => void;
}

export function PriceCell({
  ticker,
  market,
  large,
  priceState,
  livePricesKrw,
  livePricesUsd,
  priceRetrying,
  onRetryPrice,
}: PriceCellProps) {
  const krw = livePricesKrw[ticker];
  const usd = livePricesUsd[ticker];
  const priceCls = large ? "text-sm" : "text-xs";
  const retrying = priceRetrying?.has(ticker) ?? false;
  if (priceState === "loading")
    return <span className="text-gray-500 dark:text-gray-600 text-xs">조회 중</span>;
  if (krw != null) {
    if (isOverseasMarket(market) && usd != null) {
      return (
        <div>
          <div className={`text-gray-700 dark:text-gray-300 ${priceCls}`}>${usd.toFixed(2)}</div>
          <div className="text-gray-500 text-xs">≈ {fmtKrwPrice(krw)}</div>
        </div>
      );
    }
    return (
      <span className={`text-gray-700 dark:text-gray-300 ${priceCls}`}>{fmtKrwPrice(krw)}</span>
    );
  }
  return (
    <div className="flex items-center justify-end gap-1">
      <span className={`text-gray-500 dark:text-gray-600 ${priceCls}`}>—</span>
      {onRetryPrice && (
        <button
          onClick={() => onRetryPrice(ticker, market)}
          disabled={retrying}
          aria-label="현재가 재조회"
          title="현재가 재조회"
          className="text-gray-500 hover:text-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <RefreshCw size={large ? 14 : 12} className={retrying ? "animate-spin" : ""} />
        </button>
      )}
    </div>
  );
}
