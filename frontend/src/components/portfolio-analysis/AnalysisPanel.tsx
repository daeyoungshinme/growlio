import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import type { RebalancingAlert } from "@/api/alerts";
import type { Portfolio } from "@/api/portfolios";
import type { AssetAccount } from "@/api/assets";

import RebalancingTable from "@/components/rebalancing/RebalancingTable";
import { RebalancingAccountSyncSection } from "@/components/rebalancing/RebalancingAccountSyncSection";
import RebalancingStrategyCard from "@/components/rebalancing/RebalancingStrategyCard";
import AutomationStatusBar from "@/components/rebalancing/AutomationStatusBar";
import SegmentedControl from "@/components/portfolio/allocation/SegmentedControl";
import SkeletonCard from "@/components/common/SkeletonCard";
import { useAnalysisState } from "@/hooks/useAnalysisState";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";

const BacktestTab = lazy(() => import("@/components/rebalancing/BacktestTab"));

type AnalysisView = "rebalancing" | "strategy" | "backtest";

const VIEW_OPTIONS: { value: AnalysisView; label: string }[] = [
  { value: "rebalancing", label: "리밸런싱 분석" },
  { value: "strategy", label: "효율 분석" },
  { value: "backtest", label: "백테스트" },
];

interface Props {
  /** 분석 대상 포트폴리오 — 선택되면 자동으로 리밸런싱 분석을 시작한다 */
  portfolioId: string;
  portfolios: Portfolio[];
  activeAccounts: AssetAccount[];
  onOpenAlertModal: (portfolioId: string) => void;
  alertByPortfolioId: Record<string, RebalancingAlert>;
  autoOpenExecution?: boolean;
  /** 계좌 목록 로딩 완료 여부 — 자동 분석이 실시간 예수금 조회 대상 계좌를 알고 시작하도록 */
  accountsReady?: boolean;
  /** 분석이 끝나면 결과로 스크롤 — 사용자가 직접 고른 경우만. 기본 선택으로 열렸을 때 탭을 열자마자
   * 화면이 아래로 튀지 않도록(plans/64 S3) */
  scrollToResult?: boolean;
}

/** 분석·예수금 기준 계좌 — 포트폴리오에 연결 계좌가 있으면 그 계좌들, 없으면 활성 계좌 전체 */
function portfolioAccounts(portfolio: Portfolio | undefined, activeAccounts: AssetAccount[]) {
  const ids = portfolio?.account_ids;
  return ids?.length ? activeAccounts.filter((a) => ids.includes(a.id)) : activeAccounts;
}

export function AnalysisPanel({
  portfolioId,
  portfolios,
  activeAccounts,
  onOpenAlertModal,
  alertByPortfolioId,
  autoOpenExecution,
  accountsReady,
  scrollToResult = true,
}: Props) {
  const portfolio = portfolios.find((p) => p.id === portfolioId);
  const portfolioItemsSignature = JSON.stringify(portfolio?.items ?? []);
  const getDepositAccounts = useCallback(
    (id: string) =>
      portfolioAccounts(
        portfolios.find((p) => p.id === id),
        activeAccounts,
      ),
    [portfolios, activeAccounts],
  );
  const { mode, analysis, analyzing, error, cashIsLive, triggerRebalancingAnalysis, setMode } =
    useAnalysisState({
      autoAnalyzeId: portfolioId,
      selectedIdStr: portfolioId,
      portfolioItemsSignature,
      getDepositAccounts,
      accountsReady,
    });
  // 백테스트는 분석 상태(useAnalysisState)와 별개로 보여준다 — 다녀와도 리밸런싱 분석 결과가 남도록
  // 어느 포트폴리오에서 백테스트를 열었는지로 파생 — 포트폴리오를 바꾸면 자연히 리밸런싱 분석으로 돌아간다
  const [backtestFor, setBacktestFor] = useState<string | null>(null);
  const showBacktest = backtestFor === portfolioId;
  const view: AnalysisView = showBacktest ? "backtest" : (mode ?? "rebalancing");

  const analysisResultRef = useRef<HTMLDivElement>(null);
  const autoScrolledForRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    autoScrolledForRef.current = undefined;
  }, [portfolioId]);

  useEffect(() => {
    if (
      !scrollToResult ||
      !analysis ||
      analysis.portfolio_id.toString() !== portfolioId ||
      autoScrolledForRef.current === portfolioId
    ) {
      return;
    }
    autoScrolledForRef.current = portfolioId;
    const timer = setTimeout(() => {
      analysisResultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
    return () => clearTimeout(timer);
  }, [portfolioId, analysis, scrollToResult]);

  const handleRebalancingAnalysis = useCallback(() => {
    void triggerRebalancingAnalysis(portfolioId);
  }, [portfolioId, triggerRebalancingAnalysis]);
  const handleLiveAnalysis = useCallback(() => {
    void triggerRebalancingAnalysis(portfolioId, { live: true });
  }, [portfolioId, triggerRebalancingAnalysis]);

  const handleViewChange = (next: AnalysisView) => {
    if (next === "backtest") {
      setBacktestFor(portfolioId);
      return;
    }
    setBacktestFor(null);
    if (next === "strategy") {
      if (mode !== "strategy") setMode("strategy");
      return;
    }
    // 효율 분석에서 돌아오면 결과가 비워져 있으므로 다시 분석, 백테스트에서 돌아오면 기존 결과 유지
    if (mode !== "rebalancing" || !analysis) handleRebalancingAnalysis();
  };

  return (
    <div className="flex-1 min-w-0 space-y-4">
      {/* 분석 보기 — 탭 위계 3단(페이지 pill → 포트폴리오 탭 → segmented, plans/64 S3) */}
      <div className="flex items-center gap-2">
        <div className="flex-1 min-w-0">
          <SegmentedControl
            ariaLabel="분석 보기"
            stretch
            options={VIEW_OPTIONS}
            value={view}
            onChange={handleViewChange}
          />
        </div>
        {view === "rebalancing" && (
          <button
            type="button"
            onClick={handleLiveAnalysis}
            disabled={analyzing}
            aria-label="실시간 잔고로 다시 분석"
            title="실시간 잔고로 다시 분석"
            className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} flex-none justify-center px-2 rounded-lg text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 disabled:opacity-40`}
          >
            {analyzing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          </button>
        )}
      </div>

      {/* 자동화 상태 — 분석 보기와 무관하게 선택 포트폴리오당 한 번만(plans/63 P2-2) */}
      {view !== "backtest" && (
        <AutomationStatusBar
          existingAlert={alertByPortfolioId[portfolioId]}
          onOpenAlertModal={() => onOpenAlertModal(portfolioId)}
        />
      )}

      {/* 최초 분석 중(또는 계좌 로딩을 기다리는 중) — 아직 표시할 이전 결과가 없을 때만 스켈레톤 */}
      {view === "rebalancing" && !analysis && !error && <SkeletonCard rows={4} />}

      {/* 리밸런싱 결과 */}
      {view === "rebalancing" && analysis && (
        <div ref={analysisResultRef} className="card pb-20 sm:pb-0 relative">
          {analyzing && (
            <div className="flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400 mb-3">
              <Loader2 size={12} className="animate-spin" /> 재분석 중...
            </div>
          )}
          {!analyzing && error && (
            <div className="flex items-center justify-between gap-2 text-xs text-red-500 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/40 rounded-lg px-3 py-2 mb-3">
              <span>{error}</span>
              <button
                onClick={handleRebalancingAnalysis}
                className="flex-none flex items-center gap-1 font-medium hover:text-red-600 dark:hover:text-red-300 transition-colors"
              >
                <RefreshCw size={12} /> 다시 시도
              </button>
            </div>
          )}
          {(() => {
            const currentPortfolio = portfolios.find(
              (p) => p.id === analysis.portfolio_id.toString(),
            );
            const analysisAccounts = portfolioAccounts(currentPortfolio, activeAccounts);
            return (
              <>
                <RebalancingTable
                  analysis={analysis}
                  portfolioId={analysis.portfolio_id}
                  accounts={analysisAccounts}
                  alertThreshold={(() => {
                    // 서버 drift-summary와 같은 기준 — 켜진 알림의 최소 임계치, 없으면 기본값
                    const a = alertByPortfolioId[analysis.portfolio_id.toString()];
                    return a?.is_active ? a.threshold_pct : undefined;
                  })()}
                  autoOpenExecution={autoOpenExecution}
                  cashIsLive={cashIsLive}
                  onReanalyze={() => triggerRebalancingAnalysis(analysis.portfolio_id)}
                />
                <RebalancingAccountSyncSection
                  accounts={analysisAccounts}
                  onReanalyze={() => triggerRebalancingAnalysis(analysis.portfolio_id)}
                />
              </>
            );
          })()}
        </div>
      )}
      {view === "rebalancing" && error && !analysis && (
        <div className="card flex flex-col items-center justify-center gap-3 py-10 text-center">
          <p className="text-sm text-red-500">{error}</p>
          <button
            onClick={handleRebalancingAnalysis}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <RefreshCw size={13} /> 다시 시도
          </button>
        </div>
      )}

      {/* 효율 분석(팩터·프런티어) 결과 */}
      {view === "strategy" && portfolio && (
        <RebalancingStrategyCard portfolioId={portfolioId} portfolioName={portfolio.name} />
      )}

      {/* 백테스트 — 선택 포트폴리오를 기본으로 체크, 다른 포트폴리오와 비교 가능 */}
      {view === "backtest" && (
        <Suspense fallback={<SkeletonCard />}>
          <BacktestTab key={portfolioId} defaultPortfolioIds={[portfolioId]} />
        </Suspense>
      )}
    </div>
  );
}
