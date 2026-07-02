import { RebalancingAnalysis } from "@/api/rebalancing";
import { fmtKrw } from "@/utils/format";
import { PROFIT_COLOR, LOSS_COLOR } from "@/utils/colors";

interface Props {
  analysis: RebalancingAnalysis;
  cashAvailable: number;
  totalBuySummary: number;
  totalSellSummary: number;
  cashAfter: number;
}

// 핵심 요약 — 예수금 / 매도 예상 / 매수 필요 / 리밸런싱 후 예수금 2×2 그리드
export default function RebalancingSummaryCards({
  analysis,
  cashAvailable,
  totalBuySummary,
  totalSellSummary,
  cashAfter,
}: Props) {
  const cashAfterCls =
    cashAfter >= 0
      ? cashAfter < totalBuySummary * 0.05
        ? "text-amber-400"
        : "text-green-400"
      : "text-red-400";

  return (
    <div className={`rounded-xl p-3 ${cashAfter < 0 ? "bg-red-900/20 border border-red-800/40" : "bg-gray-700/60"}`}>
      <div className="text-xs text-gray-500 mb-2">
        {analysis.base_type === "STOCK_ONLY"
          ? cashAvailable > 0
            ? `기준 자산 ${fmtKrw(analysis.base_value_krw)} (주식+예수금)`
            : `기준 자산 ${fmtKrw(analysis.base_value_krw)}`
          : `기준 자산 ${fmtKrw(analysis.base_value_krw)} (전체)`}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-gray-800/60 rounded-lg p-2">
          <div className="text-xs text-gray-500 mb-0.5">예수금</div>
          <div className="text-sm font-semibold text-gray-200">{fmtKrw(cashAvailable)}</div>
        </div>
        <div className="bg-gray-800/60 rounded-lg p-2">
          <div className="text-xs text-gray-500 mb-0.5">매도 예상</div>
          <div className={`text-sm font-semibold ${totalSellSummary > 0 ? LOSS_COLOR : "text-gray-400"}`}>
            {totalSellSummary > 0 ? `+${fmtKrw(totalSellSummary)}` : "—"}
          </div>
        </div>
        <div className="bg-gray-800/60 rounded-lg p-2">
          <div className="text-xs text-gray-500 mb-0.5">매수 필요</div>
          <div className={`text-sm font-semibold ${totalBuySummary > 0 ? PROFIT_COLOR : "text-gray-400"}`}>
            {totalBuySummary > 0 ? fmtKrw(totalBuySummary) : "—"}
          </div>
        </div>
        <div className="bg-gray-800/60 rounded-lg p-2">
          <div className="text-xs text-gray-500 mb-0.5">리밸런싱 후 예수금</div>
          <div className={`text-sm font-semibold ${cashAfterCls}`}>
            {cashAfter >= 0 ? "+" : ""}
            {fmtKrw(cashAfter)}
          </div>
        </div>
      </div>
      {cashAfter < 0 && (
        <div className="text-xs text-red-400 mt-2">예수금 부족 — 매도 후 매수하거나 수량을 조정하세요</div>
      )}
    </div>
  );
}
