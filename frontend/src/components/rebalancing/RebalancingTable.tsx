import { useEffect, useRef, useState } from "react";
import { Loader2, RefreshCw, Zap } from "lucide-react";
import { ExecutionResult, RebalancingAnalysis } from "@/api/rebalancing";
import { useSyncAccounts } from "@/hooks/useSyncAccounts";
import { AssetAccount } from "@/api/assets";
import { fmtKrw } from "@/utils/format";
import { isOrderExecutableAccount } from "@/utils/accounts";
import { RebalancingExecutionModal } from "./RebalancingExecutionModal";
import ErrorBoundary from "@/components/ErrorBoundary";
import RebalancingDividendSection from "./RebalancingDividendSection";
import RebalancingDiagnosisCard from "./RebalancingDiagnosisCard";
import RebalancingSummaryCards from "./RebalancingSummaryCards";
import RebalancingWeightTable from "./RebalancingWeightTable";
import RebalancingDetailMetrics from "./RebalancingDetailMetrics";
import { calcTradeSummary, TRADING_FEE_RATE } from "./rebalancingTradeMath";

interface Props {
  analysis: RebalancingAnalysis;
  portfolioId: string;
  accounts: AssetAccount[];
  alertThreshold?: number;
  /** 같은 포트폴리오를 다시 분석 — 실행 후 계좌 동기화가 끝나면 호출한다 */
  onReanalyze?: () => void;
  /** 푸시 알림 딥링크(openExecution=1)로 진입한 경우, 분석 결과가 준비되면 실행 모달을 자동으로 연다. */
  autoOpenExecution?: boolean;
  /** 예수금이 증권사 실시간 잔고 기준인지(false면 마지막 동기화 시점 값) */
  cashIsLive?: boolean;
}

export default function RebalancingTable({
  analysis,
  portfolioId,
  accounts,
  alertThreshold,
  onReanalyze,
  autoOpenExecution,
  cashIsLive = false,
}: Props) {
  const tradableAccounts = accounts.filter((a) => isOrderExecutableAccount(a.asset_type));
  const [executionOpen, setExecutionOpen] = useState(false);

  const autoOpenRef = useRef(autoOpenExecution);
  useEffect(() => {
    if (autoOpenRef.current && analysis) {
      autoOpenRef.current = false;
      setExecutionOpen(true);
    }
  }, [analysis]);

  // 모바일 하단 고정 실행 버튼은 분석 결과가 화면에 있을 때만 띄운다 — 아래 백테스트·동기화 섹션까지
  // 스크롤해도 버튼이 남아 콘텐츠를 가리던 문제(plans/50 X7). IntersectionObserver가 없으면 항상 노출.
  const rootRef = useRef<HTMLDivElement>(null);
  const [resultsInView, setResultsInView] = useState(true);
  useEffect(() => {
    const el = rootRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setResultsInView(entry.isIntersecting));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // 주문을 실행하면 지금 보이는 분석은 실행 전 잔고 기준이 된다 — 재분석으로 analysis가 바뀔 때까지
  // "실행 전 기준" 배너로 알리고, 동기화+재분석을 한 번에 할 수 있게 한다(plans/63 P3-1)
  const [executed, setExecuted] = useState<{
    analysis: RebalancingAnalysis;
    accountIds: string[];
  } | null>(null);
  const showPreExecutionNotice = executed?.analysis === analysis;
  const { state: syncState, run: syncAccounts } = useSyncAccounts();
  const handleExecuted = (results: ExecutionResult[]) =>
    setExecuted({ analysis, accountIds: [...new Set(results.map((r) => r.account_id))] });
  const syncAndReanalyze = async () => {
    if (executed && (await syncAccounts(executed.accountIds))) onReanalyze?.();
  };

  const [now] = useState(() => Date.now());
  const minutesOld = (now - new Date(analysis.analyzed_at).getTime()) / 60000;
  const isStale = minutesOld > 10;

  const hasDividendData =
    (analysis.target_portfolio_annual_dividend ?? 0) > 0 ||
    (analysis.total_current_annual_dividend ?? analysis.current_portfolio_annual_dividend ?? 0) > 0;

  // 요약·비중테이블·거래비용 모두 calcTradeKrw 기준으로 통일 (거래 불가 항목은 calcTradeSummary가 제외)
  const { totalBuySummary, totalSellSummary } = calcTradeSummary(analysis.items);
  const cashAvailable = analysis.available_cash_krw ?? 0;
  const cashAfter = cashAvailable + totalSellSummary - totalBuySummary;
  const estFee = (totalBuySummary + totalSellSummary) * TRADING_FEE_RATE;

  return (
    <div ref={rootRef} className="space-y-4">
      {/* 리밸런싱 진단 요약 카드 */}
      <RebalancingDiagnosisCard
        analysis={analysis}
        alertThreshold={alertThreshold}
        portfolioName={analysis.portfolio_name}
      />

      {showPreExecutionNotice && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-700/40 dark:bg-amber-900/30 px-3 py-2.5 text-xs text-amber-800 dark:text-amber-300">
          <span className="flex-1">
            주문을 실행했어요 — 아래 분석은 실행 전 잔고 기준이에요.
            {syncState === "error" && " 일부 계좌 동기화에 실패했어요."}
          </span>
          {onReanalyze && (
            <button
              onClick={() => void syncAndReanalyze()}
              disabled={syncState === "syncing"}
              className="inline-flex items-center justify-center gap-1.5 self-end sm:self-auto px-3 py-1.5 rounded-lg bg-amber-600 text-white font-medium hover:bg-amber-700 disabled:opacity-50 transition-colors"
            >
              {syncState === "syncing" ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <RefreshCw size={12} />
              )}
              동기화하고 다시 분석
            </button>
          )}
        </div>
      )}

      {/* 재분석 권장 배너 — 데스크탑/모바일 공통 노출 */}
      {!showPreExecutionNotice && isStale && (
        <span className="inline-flex text-xs text-amber-600 dark:text-amber-400 bg-amber-50 border border-amber-200 dark:bg-amber-900/30 dark:border-amber-700/40 rounded-lg px-2.5 py-1">
          분석 {Math.floor(minutesOld)}분 경과 — 재분석 권장
        </span>
      )}

      {/* 실행 버튼 행 (데스크탑) */}
      <div className="hidden sm:flex items-center gap-2">
        <div className="flex items-center gap-2 ml-auto">
          {tradableAccounts.length === 0 && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              KIS·키움 증권계좌 연동 시 자동 주문 가능
            </span>
          )}
          <button
            onClick={() => setExecutionOpen(true)}
            disabled={tradableAccounts.length === 0}
            className="inline-flex items-center gap-1.5 bg-indigo-600 text-white px-4 py-1.5 text-xs rounded-lg hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium"
            title={
              tradableAccounts.length === 0
                ? "자산 › 계좌관리에서 KIS·키움 증권계좌를 연동하세요"
                : ""
            }
          >
            <Zap size={14} /> 리밸런싱 실행
          </button>
        </div>
      </div>

      {/* 요약 카드 */}
      <RebalancingSummaryCards
        analysis={analysis}
        cashAvailable={cashAvailable}
        cashIsLive={cashIsLive}
        totalBuySummary={totalBuySummary}
        totalSellSummary={totalSellSummary}
        cashAfter={cashAfter}
        estFee={estFee}
      />

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

      {/* 모바일: 하단 고정 실행 버튼 (분석 결과가 보일 때만) */}
      <div
        className={`sm:hidden fixed bottom-16 left-0 right-0 px-4 z-20 ${resultsInView ? "" : "hidden"}`}
        style={{ paddingBottom: "max(0.5rem, env(safe-area-inset-bottom, 0px))" }}
      >
        {tradableAccounts.length === 0 && (
          <div className="text-center text-xs text-gray-500 dark:text-gray-400 bg-white/90 dark:bg-gray-900/90 rounded-t-lg px-2 py-1">
            KIS·키움 증권계좌 연동 시 자동 주문 가능
          </div>
        )}
        <button
          onClick={() => setExecutionOpen(true)}
          disabled={tradableAccounts.length === 0}
          className="w-full flex items-center justify-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white py-3 rounded-xl text-sm font-semibold shadow-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title={
            tradableAccounts.length === 0
              ? "자산 › 계좌관리에서 KIS·키움 증권계좌를 연동하세요"
              : ""
          }
        >
          <Zap size={16} /> 리밸런싱 실행
        </button>
      </div>

      {executionOpen && (
        <ErrorBoundary variant="section">
          <RebalancingExecutionModal
            portfolioId={portfolioId}
            analysis={analysis}
            accounts={accounts}
            onExecuted={handleExecuted}
            onSynced={onReanalyze}
            onClose={() => setExecutionOpen(false)}
          />
        </ErrorBoundary>
      )}
    </div>
  );
}
