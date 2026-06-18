import { useMemo, useState } from "react";
import { RebalancingAnalysis } from "@/api/rebalancing";
import { fmtKrw } from "@/utils/format";
import { DividendDiffCell } from "./RebalancingCells";

interface Props {
  analysis: RebalancingAnalysis;
}

export default function RebalancingDividendSection({ analysis }: Props) {
  const [showDividendDetail, setShowDividendDetail] = useState(false);

  const currentDiv = analysis.current_portfolio_annual_dividend ?? 0;
  const targetDiv = analysis.target_portfolio_annual_dividend ?? 0;
  const totalCurrentDiv = analysis.total_current_annual_dividend ?? currentDiv;
  const divDiff = targetDiv - totalCurrentDiv;
  const divDiffPct = totalCurrentDiv > 0 ? (divDiff / totalCurrentDiv) * 100 : 0;

  const dividendItems = useMemo(
    () => analysis.items.filter((i) => i.ticker !== "CASH" && (i.dividend_yield ?? 0) > 0),
    [analysis.items],
  );

  return (
    <div className="bg-gray-700/50 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium text-gray-200">배당 분석</div>
        {dividendItems.length > 0 && (
          <button
            onClick={() => setShowDividendDetail((v) => !v)}
            className="text-xs text-gray-400 hover:text-gray-200 transition-colors"
          >
            {showDividendDetail ? "▲ 접기" : "▼ 종목별 상세"}
          </button>
        )}
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-gray-700 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">
            <span className="sm:hidden">현재 배당</span>
            <span className="hidden sm:inline">현재 연간 배당</span>
          </div>
          <div className="text-sm font-semibold text-gray-100">{fmtKrw(totalCurrentDiv)}</div>
          <div className="text-xs text-gray-500 mt-0.5 hidden sm:block">전체 보유 기준</div>
        </div>
        <div className="bg-gray-700 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">
            <span className="sm:hidden">리밸 후 배당</span>
            <span className="hidden sm:inline">리밸런싱 후 연간 배당</span>
          </div>
          <div className="text-sm font-semibold text-gray-100">{fmtKrw(targetDiv)}</div>
        </div>
        <div
          className={`col-span-1 rounded-xl p-3 text-center ${
            divDiff >= 0 ? "bg-green-900/30" : "bg-red-900/30"
          }`}
        >
          <div className="text-xs text-gray-400 mb-1">배당 증감</div>
          <div
            className={`text-sm font-semibold ${divDiff >= 0 ? "text-green-400" : "text-red-400"}`}
          >
            {divDiff >= 0 ? "+" : ""}
            {fmtKrw(divDiff)}
          </div>
          {totalCurrentDiv > 0 && (
            <div className={`text-xs ${divDiff >= 0 ? "text-green-500" : "text-red-500"}`}>
              ({divDiff >= 0 ? "+" : ""}
              {divDiffPct.toFixed(1)}%)
            </div>
          )}
        </div>
      </div>

      {/* 종목별 배당 상세 */}
      {showDividendDetail && dividendItems.length > 0 && (
        <>
          {/* 모바일 카드 */}
          <div className="sm:hidden divide-y divide-gray-700 mt-2">
            {dividendItems.map((item, idx) => (
              <div key={idx} className="py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-medium text-gray-100 text-xs truncate">{item.name}</p>
                    <p className="text-xs text-gray-400">
                      {item.ticker}
                      {item.dividend_yield != null &&
                        ` · 배당율 ${item.dividend_yield.toFixed(2)}%`}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <DividendDiffCell diff={item.annual_dividend_diff_krw ?? 0} />
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs text-gray-400 overflow-hidden">
                  <span className="truncate">
                    현재 {fmtKrw(item.annual_dividend_current_krw ?? 0)}
                  </span>
                  <span className="shrink-0">→</span>
                  <span className="truncate">
                    목표 {fmtKrw(item.annual_dividend_target_krw ?? 0)}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* 데스크탑 테이블 */}
          <div className="hidden sm:block overflow-x-auto mt-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-600 text-xs text-gray-400">
                  <th className="text-left py-2 px-3 font-medium">종목</th>
                  <th className="text-right py-2 px-3 font-medium">배당수익률</th>
                  <th className="text-right py-2 px-3 font-medium">현재 연배당</th>
                  <th className="text-right py-2 px-3 font-medium">목표 연배당</th>
                  <th className="text-right py-2 px-3 font-medium">배당 증감</th>
                </tr>
              </thead>
              <tbody>
                {dividendItems.map((item, idx) => (
                  <tr key={idx} className="border-b border-gray-700 hover:bg-gray-700">
                    <td className="py-2 px-3">
                      <div className="font-medium text-gray-100 text-xs truncate max-w-[120px]">
                        {item.name}
                      </div>
                      <div className="text-xs text-gray-400">{item.ticker}</div>
                    </td>
                    <td className="py-2 px-3 text-right text-xs text-gray-300">
                      {item.dividend_yield != null ? `${item.dividend_yield.toFixed(2)}%` : "-"}
                    </td>
                    <td className="py-2 px-3 text-right text-xs text-gray-300">
                      {fmtKrw(item.annual_dividend_current_krw ?? 0)}
                    </td>
                    <td className="py-2 px-3 text-right text-xs text-gray-300">
                      {fmtKrw(item.annual_dividend_target_krw ?? 0)}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <DividendDiffCell diff={item.annual_dividend_diff_krw ?? 0} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
