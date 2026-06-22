import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, lazy, Suspense } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { RefreshCw, ChevronDown, ChevronUp } from "lucide-react";
import Tabs from "@/components/common/Tabs";
import { syncAccount } from "@/api/assets";
import { useDividendData } from "@/hooks/useDividendData";
import StockHoldingsTable from "@/components/assets/StockHoldingsTable";
import DividendTab from "@/components/portfolio/DividendTab";
import { fmtKrwPrice } from "@/utils/format";
import { invalidateSyncData } from "@/utils/queryInvalidation";
import { useRegisterRefresh } from "@/hooks/useRegisterRefresh";
import { toast } from "@/utils/toast";
import { pnlColor } from "@/utils/colors";
import SkeletonCard from "@/components/common/SkeletonCard";
import SkeletonStatBox from "@/components/common/SkeletonStatBox";
import ErrorBoundary from "@/components/ErrorBoundary";
import { STALE_TIME, REFETCH_INTERVAL } from "@/constants/queryConfig";
import { isNativePlatform } from "@/utils/platform";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { PORTFOLIO_TABS } from "@/constants/tabs";
import type { PortfolioOverview } from "@/types";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
const TaxOptimizationCard = lazy(
  () => import("../components/portfolio-analysis/TaxOptimizationCard"),
);
const PortfolioDiagnosisCard = lazy(
  () => import("../components/portfolio-analysis/PortfolioDiagnosisCard"),
);

const TreemapChart = lazy(() => import("../components/portfolio/TreemapChart"));
const DomesticForeignBar = lazy(() => import("../components/portfolio/DomesticForeignBar"));

const CHARTS_OPEN_KEY = "portfolio:chartsOpen";
const fetchOverview = () => api.get<PortfolioOverview>("/portfolio/overview").then((r) => r.data);
const TABS = PORTFOLIO_TABS;
type Tab = (typeof TABS)[number];

export default function PortfolioPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();

  const handleRefresh = useCallback(async () => {
    await invalidateSyncData(qc);
  }, [qc]);
  useRegisterRefresh(handleRefresh);

  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("tab");

  // 구 "포트폴리오 분석" 탭 URL → /rebalancing 리다이렉트
  useEffect(() => {
    if (rawTab === "포트폴리오 분석") {
      const portfolioId = searchParams.get("portfolioId");
      const target = portfolioId ? `/rebalancing?portfolioId=${portfolioId}` : "/rebalancing";
      navigate(target, { replace: true });
    }
  }, [rawTab, searchParams, navigate]);

  const tab: Tab = TABS.includes(rawTab as Tab) ? (rawTab as Tab) : "종목 현황";

  const handleTabChange = useCallback(
    (next: Tab) => {
      setSearchParams((prev) => {
        prev.set("tab", next);
        return prev;
      }, { replace: true });
    },
    [setSearchParams],
  );
  const [syncingAll, setSyncingAll] = useState(false);
  const [syncProgress, setSyncProgress] = useState({ done: 0, total: 0 });
  const [chartsOpen, setChartsOpen] = useState(
    () => localStorage.getItem(CHARTS_OPEN_KEY) !== "false",
  );

  const handleChartsToggle = useCallback(() => {
    setChartsOpen((v) => {
      const next = !v;
      localStorage.setItem(CHARTS_OPEN_KEY, String(next));
      return next;
    });
  }, []);

  const { data, isLoading, error } = useQuery({
    queryKey: QUERY_KEYS.portfolioOverview,
    queryFn: fetchOverview,
    staleTime: STALE_TIME.EXCHANGE_RATE,
    refetchInterval: isNativePlatform() ? false : REFETCH_INTERVAL.PORTFOLIO,
  });

  const {
    dividendPositions: dividendData,
    dividendSummary: divSummary,
    dividendByTicker,
    isLoading: divLoading,
    isError: divError,
  } = useDividendData(!isLoading && !!data);

  const handleSyncAll = async () => {
    if (!data) return;
    const accounts = data.accounts.filter(
      (a) => a.asset_type.startsWith("STOCK") || a.asset_type === "CASH_OTHER",
    );
    setSyncingAll(true);
    setSyncProgress({ done: 0, total: accounts.length });
    try {
      const results = await Promise.allSettled(
        accounts.map(async (acc) => {
          try {
            await syncAccount(acc.id);
          } finally {
            setSyncProgress((p) => ({ ...p, done: p.done + 1 }));
          }
        }),
      );
      await invalidateSyncData(qc);
      const failed = results.filter((r) => r.status === "rejected").length;
      if (failed > 0) {
        toast(`${failed}개 계좌 동기화에 실패했습니다`, "error");
      } else {
        toast("전체 동기화 완료", "success");
      }
    } finally {
      setSyncingAll(false);
      setSyncProgress({ done: 0, total: 0 });
    }
  };

  const stockAccounts = useMemo(
    () =>
      data?.accounts.filter(
        (a) => a.asset_type.startsWith("STOCK") || a.asset_type === "CASH_OTHER",
      ) ?? [],
    [data],
  );

  const marketChartData = useMemo(() => {
    if (!data) return [];
    const domestic = data.domestic_stock_krw ?? 0;
    const foreign = data.foreign_stock_krw ?? 0;
    const total = domestic + foreign;
    if (total === 0) return [];
    const items = [];
    if (domestic > 0)
      items.push({ name: "국내 주식", value: domestic, pct: (domestic / total) * 100 });
    if (foreign > 0)
      items.push({ name: "해외 주식", value: foreign, pct: (foreign / total) * 100 });
    return items;
  }, [data]);

  const stockChartData = useMemo(
    () =>
      (data?.stock_allocation ?? []).map((a) => ({
        name: a.name,
        ticker: a.ticker,
        value: a.value_krw ?? 0,
        pct: a.pct,
      })),
    [data],
  );

  if (isLoading)
    return (
      <div className="space-y-6">
        <div className="card">
          <div className="grid grid-cols-2 gap-px bg-gray-100 dark:bg-gray-700 sm:flex sm:divide-x sm:divide-gray-100 sm:dark:divide-gray-700 sm:bg-transparent sm:gap-0">
            {[0, 1, 2, 3].map((i) => (
              <SkeletonStatBox key={i} />
            ))}
          </div>
        </div>
        <SkeletonCard rows={5} height="h-4" />
        <SkeletonCard rows={3} height="h-4" />
      </div>
    );
  if (error || !data)
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-sm text-red-500">데이터를 불러오지 못했습니다</p>
        <button
          onClick={() => qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolioOverview })}
          className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          다시 시도
        </button>
      </div>
    );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={handleSyncAll}
            disabled={syncingAll}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-950 disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={14} className={syncingAll ? "animate-spin" : ""} />
            {syncingAll ? `${syncProgress.done}/${syncProgress.total} 갱신 중...` : "전체 갱신"}
          </button>
          <span className="text-xs text-gray-400 dark:text-gray-500">
            {stockAccounts.length}개 증권사 계좌
          </span>
        </div>
      </div>

      {/* 상단 요약 */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-3 sm:p-5">
        <p className="text-xs tracking-wide uppercase font-semibold text-gray-400 dark:text-gray-500">
          주식 총평가액
        </p>
        <p className="text-2xl sm:text-3xl font-bold mt-1 leading-tight text-blue-600">
          {fmtKrwPrice(data.total_stock_krw)}
        </p>
        <div className="mt-2">
          <span className={`text-sm font-semibold ${pnlColor(data.unrealized_pnl_krw)}`}>
            평가손익 {data.unrealized_pnl_krw >= 0 ? "+" : ""}
            {fmtKrwPrice(data.unrealized_pnl_krw)}({data.stock_return_pct >= 0 ? "+" : ""}
            {data.stock_return_pct.toFixed(2)}%)
          </span>
        </div>
      </div>

      {/* 탭 */}
      <Tabs tabs={TABS} activeTab={tab} onChange={handleTabChange} variant="pill" />

      {tab === "종목 현황" && (
        <ErrorBoundary variant="section">
          {chartsOpen && (
            <Suspense fallback={<SkeletonCard rows={3} height="h-10" />}>
              <DomesticForeignBar items={marketChartData} />
              <TreemapChart data={stockChartData} title="종목별 비중" />
            </Suspense>
          )}
          <button
            onClick={handleChartsToggle}
            className="flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors mt-2"
          >
            {chartsOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            비중 차트 {chartsOpen ? "접기" : "펼치기"}
          </button>
          {(() => {
            const dividendMap = Object.fromEntries(
              dividendData.map((d) => [`${d.ticker}-${d.market}`, d]),
            );
            return (
              <StockHoldingsTable
                positions={data.all_positions}
                totalStock={data.total_stock_krw}
                dividendMap={dividendMap}
                divLoading={divLoading}
                divError={divError}
              />
            );
          })()}
        </ErrorBoundary>
      )}

      {tab === "배당" && (
        <ErrorBoundary variant="section">
          <DividendTab
            dividendData={dividendData}
            divLoading={divLoading}
            divSummary={divSummary}
            dividendByTicker={dividendByTicker}
            totalInvestedKrw={data?.total_invested_krw}
          />
        </ErrorBoundary>
      )}

      {tab === "세금" && (
        <ErrorBoundary variant="section">
          <Suspense fallback={<SkeletonCard rows={4} height="h-4" />}>
            <TaxOptimizationCard />
          </Suspense>
        </ErrorBoundary>
      )}

      {tab === "진단" && (
        <ErrorBoundary variant="section">
          <Suspense fallback={<SkeletonCard rows={4} height="h-4" />}>
            <PortfolioDiagnosisCard defaultExpanded />
          </Suspense>
        </ErrorBoundary>
      )}
    </div>
  );
}
