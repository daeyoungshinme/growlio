import type { CashAnalysis } from "@/hooks/useRebalancingExecution";
import { fmtKrwPrice } from "@/utils/format";

export function CashSummaryBar({ analysis }: { analysis: CashAnalysis }) {
  const { deposit, isOrderableKnown, sellProceeds, totalAvailable, buyCost, surplus } = analysis;
  if (deposit === null) return null;
  const hasSell = sellProceeds !== null && sellProceeds > 0;
  const hasBuy = buyCost !== null && buyCost > 0;
  const surplusKnown = surplus !== null;
  return (
    <div className="px-4 py-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] bg-gray-900/20 border-b border-gray-700/30">
      <span className="text-gray-500">
        {isOrderableKnown ? "주문가능" : "예수금"}{" "}
        <span className="text-gray-300">{fmtKrwPrice(deposit)}</span>
        {!isOrderableKnown && (
          <span className="text-gray-600 ml-1">(미체결 주문 시 차이 발생)</span>
        )}
      </span>
      {hasSell && (
        <span className="text-gray-500">
          + 매도예상 <span className="text-blue-400">+{fmtKrwPrice(sellProceeds!)}</span>
        </span>
      )}
      {hasSell && totalAvailable !== null && (
        <span className="text-gray-500">
          = 사용가능 <span className="text-gray-200">{fmtKrwPrice(totalAvailable)}</span>
        </span>
      )}
      {hasBuy && <span className="text-gray-600">|</span>}
      {hasBuy && (
        <span className="text-gray-500">
          매수필요 <span className="text-red-400">{fmtKrwPrice(buyCost!)}</span>
        </span>
      )}
      {surplusKnown && hasBuy && (
        <span className={surplus! >= 0 ? "text-green-400" : "text-amber-400"}>
          {surplus! >= 0
            ? `여유 +${fmtKrwPrice(surplus!)}`
            : `부족 ${fmtKrwPrice(Math.abs(surplus!))}`}
        </span>
      )}
    </div>
  );
}
