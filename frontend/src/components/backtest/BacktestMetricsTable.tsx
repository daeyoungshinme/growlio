import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { PortfolioMetrics } from "@/api/backtest";
import { pnlColor, LOSS_COLOR } from "@/utils/colors";
import Tooltip from "@/components/common/Tooltip";

const COLORS = ["#2563EB", "#16A34A", "#D97706", "#DC2626", "#7C3AED", "#0891B2", "#DB2777", "#059669"];

interface Props {
  metrics: PortfolioMetrics[];
}

function fmt(n: number, suffix = "%") {
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}${suffix}`;
}

function bestIdx(values: number[], higherIsBetter: boolean): number {
  if (values.length <= 1) return 0;
  return values.reduce((best, v, i) =>
    (higherIsBetter ? v > values[best] : v < values[best]) ? i : best, 0);
}

const HIGHLIGHT = "bg-blue-50 dark:bg-blue-950/40 rounded";

function TooltipLabel({ label, tip }: { label: string; tip: string }) {
  return (
    <Tooltip content={tip} position="top">
      <span className="cursor-help underline decoration-dotted decoration-gray-400">{label}</span>
    </Tooltip>
  );
}

export default function BacktestMetricsTable({ metrics }: Props) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  if (!metrics.length) return null;

  const bTotal   = bestIdx(metrics.map((m) => m.total_return_pct), true);
  const bCagr    = bestIdx(metrics.map((m) => m.cagr_pct), true);
  const bMdd     = bestIdx(metrics.map((m) => m.mdd_pct), false);
  const bSharpe  = bestIdx(metrics.map((m) => m.sharpe_ratio), true);
  const bVol     = bestIdx(metrics.map((m) => m.volatility_pct), false);
  const bSortino = bestIdx(metrics.map((m) => m.sortino_ratio), true);

  return (
    <div>
      <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-2">성과 지표 비교</p>

      {/* 모바일 카드 뷰 */}
      <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700">
        {metrics.map((m, i) => (
          <div key={m.name} className="py-2.5">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                <p className="font-medium text-gray-800 dark:text-gray-200 text-sm truncate">{m.name}</p>
              </div>
              <p className={`text-sm font-semibold shrink-0 ${pnlColor(m.total_return_pct)}`}>{fmt(m.total_return_pct)}</p>
            </div>
            <div className="flex items-center gap-3 mt-1 text-xs text-gray-400 dark:text-gray-500 flex-wrap pl-3.5">
              <span>CAGR <span className={pnlColor(m.cagr_pct)}>{fmt(m.cagr_pct)}</span></span>
              <span>MDD <span className={LOSS_COLOR}>-{m.mdd_pct.toFixed(2)}%</span></span>
              {showAdvanced && (
                <>
                  <span title="변동성 1단위당 초과 수익률 (높을수록 효율적)">Sharpe {m.sharpe_ratio.toFixed(3)}</span>
                  <span>변동성 {m.volatility_pct.toFixed(2)}%</span>
                  <span title="하락 변동성 대비 수익률 (높을수록 손실 관리 우수)">Sortino {m.sortino_ratio.toFixed(3)}</span>
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 데스크탑 테이블 */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-700">
              <th className="py-1.5 px-2 text-left font-medium text-gray-400 dark:text-gray-500 uppercase">포트폴리오</th>
              <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">총수익률</th>
              <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase">
                <TooltipLabel label="CAGR" tip="복리 기준 연평균 수익률" />
              </th>
              <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase">
                <TooltipLabel label="MDD" tip="투자 기간 중 최고점에서 최대로 떨어진 손실 비율" />
              </th>
              {showAdvanced && (
                <>
                  <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">
                    <TooltipLabel label="Sharpe" tip="변동성 1단위당 초과 수익률 (높을수록 효율적)" />
                  </th>
                  <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">
                    <TooltipLabel label="변동성" tip="연간 수익률 표준편차 — 낮을수록 가격 변동이 적음" />
                  </th>
                  <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">
                    <TooltipLabel label="Sortino" tip="하락 변동성 대비 수익률 (손실 방어력 지표)" />
                  </th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {metrics.map((m, i) => (
              <tr key={m.name} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                <td className="py-2 px-2 font-medium text-gray-800 dark:text-gray-200 whitespace-nowrap">
                  <span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                  {m.name}
                </td>
                <td className={`py-2 px-2 text-right font-medium whitespace-nowrap ${pnlColor(m.total_return_pct)} ${i === bTotal ? HIGHLIGHT : ""}`}>
                  {fmt(m.total_return_pct)}
                </td>
                <td className={`py-2 px-2 text-right whitespace-nowrap ${pnlColor(m.cagr_pct)} ${i === bCagr ? HIGHLIGHT : ""}`}>
                  {fmt(m.cagr_pct)}
                </td>
                <td className={`py-2 px-2 text-right ${LOSS_COLOR} whitespace-nowrap ${i === bMdd ? HIGHLIGHT : ""}`}>
                  -{m.mdd_pct.toFixed(2)}%
                </td>
                {showAdvanced && (
                  <>
                    <td className={`py-2 px-2 text-right text-gray-700 dark:text-gray-300 whitespace-nowrap ${i === bSharpe ? HIGHLIGHT : ""}`}>
                      {m.sharpe_ratio.toFixed(3)}
                    </td>
                    <td className={`py-2 px-2 text-right text-gray-500 dark:text-gray-400 whitespace-nowrap ${i === bVol ? HIGHLIGHT : ""}`}>
                      {m.volatility_pct.toFixed(2)}%
                    </td>
                    <td className={`py-2 px-2 text-right text-gray-700 dark:text-gray-300 whitespace-nowrap ${i === bSortino ? HIGHLIGHT : ""}`}>
                      {m.sortino_ratio.toFixed(3)}
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 상세 지표 토글 */}
      <button
        onClick={() => setShowAdvanced((v) => !v)}
        className="mt-2 flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
      >
        {showAdvanced ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        {showAdvanced ? "기본 지표만 보기" : "상세 지표 보기 (Sharpe · 변동성 · Sortino)"}
      </button>
    </div>
  );
}
