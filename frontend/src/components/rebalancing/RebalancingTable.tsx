import { useState } from "react";
import { ExecutionResult, RebalancingAnalysis, RebalancingItem } from "../../api/rebalancing";
import { AssetAccount } from "../../api/assets";
import { fmtKrw } from "../../utils/format";
import { RebalancingExecutionModal } from "./RebalancingExecutionModal";

function DiffCell({ diff }: { diff: number }) {
  if (diff === 0) return <span className="text-gray-400">-</span>;
  const isBuy = diff > 0;
  return (
    <span className={`font-medium ${isBuy ? "text-red-500" : "text-blue-500"}`}>
      {isBuy ? "+" : ""}{fmtKrw(diff)}
    </span>
  );
}

function WeightDiffBadge({ diff }: { diff: number }) {
  if (Math.abs(diff) < 0.1) return <span className="text-gray-400 text-xs">±0%</span>;
  const isBuy = diff > 0;
  return (
    <span className={`text-xs font-medium ${isBuy ? "text-red-500" : "text-blue-500"}`}>
      {isBuy ? "▲" : "▼"} {Math.abs(diff).toFixed(1)}%
    </span>
  );
}

function WeightBar({ current, target }: { current: number; target: number }) {
  const max = Math.max(current, target, 5);
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-2 bg-gray-600 rounded-full overflow-hidden relative">
        {/* 현재 비중 */}
        <div
          className="absolute inset-y-0 left-0 bg-blue-400 rounded-full"
          style={{ width: `${Math.min((current / max) * 100, 100)}%` }}
        />
        {/* 목표 비중 (outline 효과) */}
        <div
          className="absolute inset-y-0 left-0 border-r-2 border-orange-400"
          style={{ width: `${Math.min((target / max) * 100, 100)}%` }}
        />
      </div>
      <span className="text-xs text-gray-400 w-8 text-right">{target.toFixed(0)}%</span>
    </div>
  );
}

function SharesCell({ item }: { item: RebalancingItem }) {
  if (item.ticker === "CASH" || item.shares_to_trade === null) return <span className="text-gray-400">-</span>;
  const shares = item.shares_to_trade;
  if (shares === 0) return <span className="text-gray-400">0</span>;
  const isBuy = shares > 0;
  return (
    <span className={`font-medium text-xs ${isBuy ? "text-red-500" : "text-blue-500"}`}>
      {isBuy ? "+" : ""}{shares.toFixed(0)}주
    </span>
  );
}

function DividendDiffCell({ diff }: { diff: number }) {
  if (diff === 0) return <span className="text-gray-400">-</span>;
  const isIncrease = diff > 0;
  return (
    <span className={`font-medium text-xs ${isIncrease ? "text-green-400" : "text-red-400"}`}>
      {isIncrease ? "+" : ""}{fmtKrw(diff)}
    </span>
  );
}

function Return10yCell({ item }: { item: import("../../api/rebalancing").RebalancingItem }) {
  if (item.ticker === "CASH") return <span className="text-gray-500">-</span>;
  const cagr = item.cagr_10y_pct;
  const total = item.return_10y_pct;
  if (cagr == null || total == null) return <span className="text-gray-500">—</span>;
  const isPos = cagr >= 0;
  const colorClass = isPos ? "text-red-400" : "text-blue-400";
  const years = item.actual_years_10y;
  const yearLabel = years != null && years < 9.5 ? `*${years.toFixed(1)}년` : "10년";
  return (
    <div className="text-right">
      <div className={`font-medium text-xs ${colorClass}`}>
        {isPos ? "+" : ""}{cagr.toFixed(1)}% /yr
      </div>
      <div className="text-xs text-gray-500">
        ({isPos ? "+" : ""}{total.toFixed(0)}%, {yearLabel})
      </div>
    </div>
  );
}

interface Props {
  analysis: RebalancingAnalysis;
  portfolioId: string;
  accounts: AssetAccount[];
  onExecuted?: (results: ExecutionResult[]) => void;
}

function CagrCard({ label, cagr }: { label: string; cagr: number | null | undefined }) {
  if (cagr == null) return null;
  const isPos = cagr >= 0;
  return (
    <div className="bg-gray-700 rounded-xl p-3 text-center">
      <div className="text-xs text-gray-400 mb-1">{label}</div>
      <div className={`text-sm font-semibold ${isPos ? "text-red-400" : "text-blue-400"}`}>
        {isPos ? "+" : ""}{cagr.toFixed(1)}% /yr
      </div>
      <div className="text-xs text-gray-500">10년 CAGR</div>
    </div>
  );
}

export default function RebalancingTable({ analysis, portfolioId, accounts, onExecuted }: Props) {
  const kisAccounts = accounts.filter((a) => a.asset_type === "STOCK_KIS");
  const [showDividendDetail, setShowDividendDetail] = useState(false);
  const [executionOpen, setExecutionOpen] = useState(false);

  const currentDiv = analysis.current_portfolio_annual_dividend ?? 0;
  const targetDiv = analysis.target_portfolio_annual_dividend ?? 0;
  const totalCurrentDiv = analysis.total_current_annual_dividend ?? currentDiv;
  const divDiff = targetDiv - totalCurrentDiv;
  const divDiffPct = totalCurrentDiv > 0 ? (divDiff / totalCurrentDiv) * 100 : 0;
  const hasDividendData = targetDiv > 0 || totalCurrentDiv > 0;
  const hasCagrData =
    analysis.target_weighted_cagr_10y_pct != null || analysis.current_weighted_cagr_10y_pct != null;

  const dividendItems = analysis.items.filter(
    (i) => i.ticker !== "CASH" && (i.dividend_yield ?? 0) > 0
  );

  return (
    <div className="space-y-4">
      {/* 실행 버튼 — KIS 계좌 없으면 disabled */}
      <div className="flex justify-end items-center gap-2">
        {kisAccounts.length === 0 && (
          <span className="text-xs text-gray-500">
            KIS 증권계좌 연동 시 자동 주문 가능
          </span>
        )}
        <button
          onClick={() => setExecutionOpen(true)}
          disabled={kisAccounts.length === 0}
          className="bg-indigo-600 text-white px-4 py-1.5 text-xs rounded-lg hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium"
          title={kisAccounts.length === 0 ? "자산관리에서 KIS 증권계좌를 연동하세요" : ""}
        >
          ⚡ 리밸런싱 실행
        </button>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-gray-700 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">기준 자산</div>
          <div className="text-sm font-semibold text-gray-100">{fmtKrw(analysis.base_value_krw)}</div>
          <div className="text-xs text-gray-500">{analysis.base_type === "STOCK_ONLY" ? "주식 자산" : "전체 자산"}</div>
        </div>
        <div className="bg-red-900/30 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">총 매수 필요</div>
          <div className="text-sm font-semibold text-red-500">
            {fmtKrw(analysis.items.filter((i) => i.diff_krw > 0).reduce((s, i) => s + i.diff_krw, 0))}
          </div>
        </div>
        <div className="bg-blue-900/30 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">총 매도 필요</div>
          <div className="text-sm font-semibold text-blue-500">
            {fmtKrw(Math.abs(analysis.items.filter((i) => i.diff_krw < 0).reduce((s, i) => s + i.diff_krw, 0)))}
          </div>
        </div>
      </div>

      {/* 포트폴리오 10년 수익률 요약 */}
      {hasCagrData && (
        <div className="grid grid-cols-2 gap-3">
          <CagrCard label="현재 포트폴리오 CAGR" cagr={analysis.current_weighted_cagr_10y_pct} />
          <CagrCard label="목표 포트폴리오 CAGR" cagr={analysis.target_weighted_cagr_10y_pct} />
        </div>
      )}

      {/* 리밸런싱 테이블 */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700 text-xs text-gray-400">
              <th className="text-left py-2 px-3 font-medium">종목</th>
              <th className="text-right py-2 px-3 font-medium">현재 비중</th>
              <th className="text-left py-2 px-3 font-medium">목표 비중</th>
              <th className="text-right py-2 px-3 font-medium">차이</th>
              <th className="text-right py-2 px-3 font-medium">현재 금액</th>
              <th className="text-right py-2 px-3 font-medium">목표 금액</th>
              <th className="text-right py-2 px-3 font-medium">매수/매도</th>
              <th className="text-right py-2 px-3 font-medium">주수</th>
              <th className="text-right py-2 px-3 font-medium">10년 수익률</th>
            </tr>
          </thead>
          <tbody>
            {analysis.items.map((item, idx) => (
              <tr key={idx} className="border-b border-gray-700 hover:bg-gray-700">
                <td className="py-3 px-3">
                  <div className="font-medium text-gray-100 truncate max-w-[120px]">{item.name}</div>
                  <div className="text-xs text-gray-400">{item.ticker}</div>
                </td>
                <td className="py-3 px-3 text-right text-gray-300">
                  {item.current_weight_pct.toFixed(1)}%
                </td>
                <td className="py-3 px-3">
                  <WeightBar current={item.current_weight_pct} target={item.target_weight_pct} />
                </td>
                <td className="py-3 px-3 text-right">
                  <WeightDiffBadge diff={item.weight_diff_pct} />
                </td>
                <td className="py-3 px-3 text-right text-gray-300">{fmtKrw(item.current_value_krw)}</td>
                <td className="py-3 px-3 text-right text-gray-300">{fmtKrw(item.target_value_krw)}</td>
                <td className="py-3 px-3 text-right">
                  <DiffCell diff={item.diff_krw} />
                </td>
                <td className="py-3 px-3 text-right">
                  <SharesCell item={item} />
                </td>
                <td className="py-3 px-3">
                  <Return10yCell item={item} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 배당 분석 섹션 */}
      {hasDividendData && (
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
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-gray-700 rounded-xl p-3 text-center">
              <div className="text-xs text-gray-400 mb-1">현재 연간 배당</div>
              <div className="text-sm font-semibold text-gray-100">{fmtKrw(totalCurrentDiv)}</div>
              <div className="text-xs text-gray-500 mt-0.5">전체 보유 기준</div>
            </div>
            <div className="bg-gray-700 rounded-xl p-3 text-center">
              <div className="text-xs text-gray-400 mb-1">리밸런싱 후 연간 배당</div>
              <div className="text-sm font-semibold text-gray-100">{fmtKrw(targetDiv)}</div>
            </div>
            <div className={`rounded-xl p-3 text-center ${divDiff >= 0 ? "bg-green-900/30" : "bg-red-900/30"}`}>
              <div className="text-xs text-gray-400 mb-1">배당 증감</div>
              <div className={`text-sm font-semibold ${divDiff >= 0 ? "text-green-400" : "text-red-400"}`}>
                {divDiff >= 0 ? "+" : ""}{fmtKrw(divDiff)}
              </div>
              {totalCurrentDiv > 0 && (
                <div className={`text-xs ${divDiff >= 0 ? "text-green-500" : "text-red-500"}`}>
                  ({divDiff >= 0 ? "+" : ""}{divDiffPct.toFixed(1)}%)
                </div>
              )}
            </div>
          </div>

          {/* 종목별 배당 상세 테이블 */}
          {showDividendDetail && dividendItems.length > 0 && (
            <div className="overflow-x-auto mt-2">
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
                        <div className="font-medium text-gray-100 text-xs truncate max-w-[120px]">{item.name}</div>
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
          )}
        </div>
      )}

      {/* 미추적 보유 종목 경고 */}
      {analysis.untracked_holdings.length > 0 && (
        <div className="bg-amber-900/20 border border-amber-700/50 rounded-xl p-4">
          <div className="text-sm font-medium text-amber-300 mb-2">
            ⚠ 목표 포트폴리오에 없는 보유 종목 ({analysis.untracked_holdings.length}개)
          </div>
          <div className="space-y-1">
            {analysis.untracked_holdings.map((h, idx) => (
              <div key={idx} className="flex items-center justify-between text-xs text-amber-400">
                <span>
                  <span className="font-medium">{h.name}</span>
                  <span className="ml-1 text-amber-500">{h.ticker}</span>
                </span>
                <span>{fmtKrw(h.current_value_krw)} ({h.current_weight_pct.toFixed(1)}%)</span>
              </div>
            ))}
          </div>
          <div className="text-xs text-amber-500 mt-2">
            이 종목들은 목표 포트폴리오에 포함되지 않았습니다. 매도를 고려하거나 목표 포트폴리오에 추가하세요.
          </div>
        </div>
      )}

      <div className="text-xs text-gray-500 text-right">
        분석 시점: {new Date(analysis.analyzed_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}
      </div>

      {executionOpen && (
        <RebalancingExecutionModal
          portfolioId={portfolioId}
          analysis={analysis}
          accounts={accounts}
          onExecuted={onExecuted}
          onClose={() => setExecutionOpen(false)}
        />
      )}
    </div>
  );
}
