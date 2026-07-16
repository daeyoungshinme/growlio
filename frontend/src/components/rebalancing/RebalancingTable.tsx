import { useEffect, useRef, useState } from "react";
import { ExecutionResult, RebalancingAnalysis } from "@/api/rebalancing";
import { AssetAccount } from "@/api/assets";
import { fmtKrw } from "@/utils/format";
import { RebalancingExecutionModal } from "./RebalancingExecutionModal";
import ErrorBoundary from "@/components/ErrorBoundary";
import RebalancingDividendSection from "./RebalancingDividendSection";
import RebalancingDiagnosisCard from "./RebalancingDiagnosisCard";
import RebalancingSummaryCards from "./RebalancingSummaryCards";
import RebalancingTradePlanPanel from "./RebalancingTradePlanPanel";
import RebalancingWeightTable from "./RebalancingWeightTable";
import RebalancingDetailMetrics from "./RebalancingDetailMetrics";
import { calcTradeKrw } from "./rebalancingTradeMath";

interface Props {
  analysis: RebalancingAnalysis;
  portfolioId: string;
  accounts: AssetAccount[];
  alertThreshold?: number;
  onExecuted?: (results: ExecutionResult[]) => void;
  /** 진단 탭에서 기준 포트폴리오에 추천 비중을 적용한 직후 마운트된 경우, 분석 결과가 준비되면 실행 모달을 자동으로 연다. */
  autoOpenExecution?: boolean;
}

export default function RebalancingTable({
  analysis,
  portfolioId,
  accounts,
  alertThreshold,
  onExecuted,
  autoOpenExecution,
}: Props) {
  const kisAccounts = accounts.filter(
    (a) => a.asset_type === "STOCK_KIS" || a.asset_type === "STOCK_KIWOOM",
  );
  const [executionOpen, setExecutionOpen] = useState(false);

  const autoOpenRef = useRef(autoOpenExecution);
  useEffect(() => {
    if (autoOpenRef.current && analysis) {
      autoOpenRef.current = false;
      setExecutionOpen(true);
    }
  }, [analysis]);

  const [now] = useState(() => Date.now());
  const minutesOld = (now - new Date(analysis.analyzed_at).getTime()) / 60000;
  const isStale = minutesOld > 10;

  const hasDividendData =
    (analysis.target_portfolio_annual_dividend ?? 0) > 0 ||
    (analysis.total_current_annual_dividend ?? analysis.current_portfolio_annual_dividend ?? 0) > 0;

  // 요약·거래계획·거래비용 모두 calcTradeKrw 기준으로 통일
  const totalBuySummary = analysis.items
    .filter((i) => i.diff_krw > 0)
    .reduce((s, i) => s + calcTradeKrw(i), 0);
  const totalSellSummary = analysis.items
    .filter((i) => i.diff_krw < 0)
    .reduce((s, i) => s + calcTradeKrw(i), 0);
  const cashAvailable = analysis.available_cash_krw ?? 0;
  const cashAfter = cashAvailable + totalSellSummary - totalBuySummary;

  return (
    <div className="space-y-4">
      {/* 리밸런싱 진단 요약 카드 */}
      <RebalancingDiagnosisCard
        analysis={analysis}
        alertThreshold={alertThreshold}
        onExecute={kisAccounts.length > 0 ? () => setExecutionOpen(true) : undefined}
      />

      {/* 실행 버튼 행 (데스크탑) */}
      <div className="hidden sm:flex items-center gap-2">
        {isStale && (
          <span className="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 border border-amber-200 dark:bg-amber-900/30 dark:border-amber-700/40 rounded-lg px-2.5 py-1">
            분석 {Math.floor(minutesOld)}분 경과 — 재분석 권장
          </span>
        )}
        <div className="flex items-center gap-2 ml-auto">
          {kisAccounts.length === 0 && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              KIS 증권계좌 연동 시 자동 주문 가능
            </span>
          )}
          <button
            onClick={() => setExecutionOpen(true)}
            disabled={kisAccounts.length === 0}
            className="inline-flex bg-indigo-600 text-white px-4 py-1.5 text-xs rounded-lg hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium"
            title={kisAccounts.length === 0 ? "자산관리에서 KIS 증권계좌를 연동하세요" : ""}
          >
            ⚡ 리밸런싱 실행
          </button>
        </div>
      </div>

      {/* 요약 카드 */}
      <div className="space-y-2">
        <RebalancingSummaryCards
          analysis={analysis}
          cashAvailable={cashAvailable}
          totalBuySummary={totalBuySummary}
          totalSellSummary={totalSellSummary}
          cashAfter={cashAfter}
        />
        <RebalancingTradePlanPanel
          items={analysis.items}
          totalBuySummary={totalBuySummary}
          totalSellSummary={totalSellSummary}
        />
      </div>

      {/* 리밸런싱 비중 테이블 */}
      <RebalancingWeightTable items={analysis.items} />

      {/* 상세 지표 (집중도 · CAGR) — 접기/펼치기 */}
      <RebalancingDetailMetrics analysis={analysis} />

      {/* 배당 분석 섹션 */}
      {hasDividendData && <RebalancingDividendSection analysis={analysis} />}

      {/* 미추적 보유 종목 */}
      {(analysis.untracked_holdings ?? []).length > 0 && (
        <div className="bg-amber-50 border border-amber-200 dark:bg-amber-900/20 dark:border-amber-700/30 rounded-xl p-4">
          <div className="text-xs font-medium text-amber-600 dark:text-amber-400 mb-2">
            포트폴리오 미포함 보유 종목 ({(analysis.untracked_holdings ?? []).length}개)
          </div>
          <div className="space-y-1.5">
            {(analysis.untracked_holdings ?? []).map((h, idx) => (
              <div key={idx} className="flex items-center justify-between text-xs">
                <div className="min-w-0">
                  <span className="font-medium text-gray-800 dark:text-gray-200 truncate">
                    {h.name}
                  </span>
                  <span className="text-gray-500 dark:text-gray-400 ml-1.5">{h.ticker}</span>
                </div>
                <div className="text-right shrink-0 ml-3">
                  <span className="text-gray-700 dark:text-gray-300">
                    {fmtKrw(h.current_value_krw)}
                  </span>
                  <span className="text-gray-500 dark:text-gray-400 ml-1">
                    ({h.current_weight_pct.toFixed(1)}%)
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-xs text-gray-500 dark:text-gray-400 text-right">
        분석 시점:{" "}
        {new Date(analysis.analyzed_at).toLocaleTimeString("ko-KR", {
          hour: "2-digit",
          minute: "2-digit",
        })}
      </div>

      {/* 모바일: 하단 고정 실행 버튼 */}
      <div
        className="sm:hidden fixed bottom-16 left-0 right-0 px-4 z-20"
        style={{ paddingBottom: "max(0.5rem, env(safe-area-inset-bottom, 0px))" }}
      >
        <button
          onClick={() => setExecutionOpen(true)}
          disabled={kisAccounts.length === 0}
          className="w-full bg-indigo-600 hover:bg-indigo-500 text-white py-3 rounded-xl text-sm font-semibold shadow-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title={kisAccounts.length === 0 ? "자산관리에서 KIS 증권계좌를 연동하세요" : ""}
        >
          ⚡ 리밸런싱 실행
        </button>
      </div>

      {executionOpen && (
        <ErrorBoundary variant="section">
          <RebalancingExecutionModal
            portfolioId={portfolioId}
            analysis={analysis}
            accounts={accounts}
            onExecuted={onExecuted}
            onClose={() => setExecutionOpen(false)}
          />
        </ErrorBoundary>
      )}
    </div>
  );
}
