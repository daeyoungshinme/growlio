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
}

export function PriceCell({ ticker, market, large, priceState, livePricesKrw, livePricesUsd }: PriceCellProps) {
  const krw = livePricesKrw[ticker];
  const usd = livePricesUsd[ticker];
  const priceCls = large ? "text-sm" : "text-[11px]";
  if (priceState === "loading") return <span className="text-gray-600 text-[11px]">조회 중</span>;
  if (krw != null) {
    if (isOverseasMarket(market) && usd != null) {
      return (
        <div>
          <div className={`text-gray-300 ${priceCls}`}>${usd.toFixed(2)}</div>
          <div className="text-gray-500 text-[11px]">≈ {fmtKrwPrice(krw)}</div>
        </div>
      );
    }
    return <span className={`text-gray-300 ${priceCls}`}>{fmtKrwPrice(krw)}</span>;
  }
  return <span className={`text-gray-600 ${priceCls}`}>—</span>;
}
