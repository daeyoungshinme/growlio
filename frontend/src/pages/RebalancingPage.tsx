import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchMarketSignal } from "@/api/marketSignals";
import { fetchPortfolioRisk, fetchCurrencyExposure } from "@/api/risk";
import type { PortfolioRiskMetrics, CurrencyExposure } from "@/api/risk";
import SkeletonCard from "@/components/common/SkeletonCard";
import Tabs from "@/components/common/Tabs";
import ErrorBoundary from "@/components/ErrorBoundary";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

const RebalancingStatusCard = lazy(
  () => import("../components/dashboard/RebalancingStatusCard"),
);
const MarketSignalBanner = lazy(
  () => import("../components/rebalancing/MarketSignalBanner"),
);
const PortfolioManageTab = lazy(
  () => import("../components/portfolio-analysis/PortfolioManageTab"),
);
const PortfolioExecutionTab = lazy(
  () => import("../components/portfolio-analysis/PortfolioExecutionTab"),
);
const RebalancingHistoryTab = lazy(
  () => import("../components/rebalancing/RebalancingHistoryTab"),
);
const BacktestTab = lazy(
  () => import("../components/rebalancing/BacktestTab"),
);

const REBALANCING_PAGE_TABS = ["진단", "포트폴리오", "백테스팅", "이력"] as const;
type RebalancingPageTab = (typeof REBALANCING_PAGE_TABS)[number];

function RiskMetricsCard({ metrics }: { metrics: PortfolioRiskMetrics }) {
  if (!metrics.data_available) return null;
  const diversityColor =
    metrics.diversification_score >= 70 ? "text-green-600 dark:text-green-400"
    : metrics.diversification_score >= 40 ? "text-yellow-600 dark:text-yellow-400"
    : "text-red-600 dark:text-red-400";
  return (
    <div className="card">
      <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-3">포트폴리오 위험 지표</p>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2.5">
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">VaR (95%)</p>
          <p className="text-sm font-semibold text-red-600 dark:text-red-400">
            {metrics.var_95_pct.toFixed(2)}%
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">연간 변동성</p>
          <p className="text-sm font-semibold text-gray-700 dark:text-gray-300">
            {metrics.annualized_volatility_pct.toFixed(1)}%
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">S&amp;P 500 베타</p>
          <p className="text-sm font-semibold text-gray-700 dark:text-gray-300">
            {metrics.beta_sp500.toFixed(2)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">분산도 점수</p>
          <p className={`text-sm font-semibold ${diversityColor}`}>
            {metrics.diversification_score}/100
          </p>
        </div>
      </div>
      {metrics.note && (
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-2.5 leading-relaxed">{metrics.note}</p>
      )}
    </div>
  );
}

function CurrencyExposureCard({ exposure }: { exposure: CurrencyExposure }) {
  const bars: { label: string; pct: number; color: string }[] = [
    { label: "KRW", pct: exposure.krw_pct, color: "bg-blue-500" },
    { label: "USD", pct: exposure.usd_pct, color: "bg-green-500" },
    ...(exposure.other_pct > 0 ? [{ label: "기타", pct: exposure.other_pct, color: "bg-gray-400" }] : []),
  ];
  return (
    <div className="card">
      <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-3">통화 노출</p>
      <div className="space-y-2">
        {bars.map(({ label, pct, color }) => (
          <div key={label}>
            <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
              <span>{label}</span>
              <span className="font-medium">{pct.toFixed(1)}%</span>
            </div>
            <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${color}`}
                style={{ width: `${Math.min(pct, 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function RebalancingPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const portfolioId = searchParams.get("portfolioId") ?? undefined;
  const rawTab = searchParams.get("rtab");
  const [localTab, setLocalTab] = useState<RebalancingPageTab>(
    REBALANCING_PAGE_TABS.includes(rawTab as RebalancingPageTab)
      ? (rawTab as RebalancingPageTab)
      : "진단",
  );

  const handleTabChange = useCallback(
    (tab: RebalancingPageTab) => {
      setLocalTab(tab);
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("rtab", tab);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const handlePortfolioChange = useCallback(
    (id: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("portfolioId", id);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const handlePortfolioSelectFromDiagnosis = useCallback(
    (id: string) => {
      handlePortfolioChange(id);
      handleTabChange("포트폴리오");
    },
    [handlePortfolioChange, handleTabChange],
  );

  const executionRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!portfolioId || localTab !== "포트폴리오") return;
    const timer = setTimeout(() => {
      executionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
    return () => clearTimeout(timer);
  }, [portfolioId, localTab]);

  const { data: signal } = useQuery({
    queryKey: QUERY_KEYS.marketSignal,
    queryFn: fetchMarketSignal,
    staleTime: STALE_TIME.LONG,
  });

  const { data: riskMetrics } = useQuery({
    queryKey: QUERY_KEYS.portfolioRisk(),
    queryFn: () => fetchPortfolioRisk(),
    staleTime: STALE_TIME.LONG,
    enabled: localTab === "진단",
  });

  const { data: currencyExposure } = useQuery({
    queryKey: QUERY_KEYS.currencyExposure,
    queryFn: fetchCurrencyExposure,
    staleTime: STALE_TIME.LONG,
    enabled: localTab === "진단",
  });

  return (
    <div className="flex flex-col min-h-full gap-4">
      <div className="px-1">
        <Tabs
          tabs={REBALANCING_PAGE_TABS}
          activeTab={localTab}
          onChange={handleTabChange}
          variant="pill"
        />
      </div>

      <div className="flex-1 flex flex-col gap-4">
        {/* ── 진단 탭: 시장신호 + 전체 포트폴리오 드리프트 현황 ── */}
        {localTab === "진단" && (
          <>
            {signal && (
              <ErrorBoundary variant="section">
                <Suspense fallback={<SkeletonCard rows={1} />}>
                  <MarketSignalBanner signal={signal} />
                </Suspense>
              </ErrorBoundary>
            )}
            <ErrorBoundary variant="section">
              <Suspense fallback={<SkeletonCard />}>
                <RebalancingStatusCard
                  marketSignal={signal ?? undefined}
                  onPortfolioSelect={handlePortfolioSelectFromDiagnosis}
                  hideSignalBanner={true}
                  showAllInsights={true}
                />
              </Suspense>
            </ErrorBoundary>
            {riskMetrics && <RiskMetricsCard metrics={riskMetrics} />}
            {currencyExposure && <CurrencyExposureCard exposure={currencyExposure} />}
          </>
        )}

        {/* ── 포트폴리오 탭: 목록 관리 + 분석/실행 ── */}
        {localTab === "포트폴리오" && (
          <>
            <Suspense fallback={<SkeletonCard />}>
              <PortfolioManageTab
                selectedPortfolioId={portfolioId}
                onAnalyze={handlePortfolioChange}
              />
            </Suspense>
            {portfolioId && (
              <div ref={executionRef}>
                <Suspense fallback={<SkeletonCard />}>
                  <PortfolioExecutionTab portfolioId={portfolioId} />
                </Suspense>
              </div>
            )}
          </>
        )}

        {/* ── 백테스팅 탭 ── */}
        {localTab === "백테스팅" && (
          <ErrorBoundary variant="section">
            <Suspense fallback={<SkeletonCard />}>
              <BacktestTab />
            </Suspense>
          </ErrorBoundary>
        )}

        {/* ── 이력 탭 ── */}
        {localTab === "이력" && (
          <Suspense fallback={<SkeletonCard />}>
            <RebalancingHistoryTab />
          </Suspense>
        )}
      </div>
    </div>
  );
}
