import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import Tabs from "../components/common/Tabs";
import { api } from "../api/client";
import { syncAccount } from "../api/assets";
import PortfolioAnalysisTab from "../components/portfolio-analysis/PortfolioAnalysisTab";
import StockHoldingsTable from "../components/assets/StockHoldingsTable";
import TreemapChart from "../components/portfolio/TreemapChart";
import DomesticForeignBar from "../components/portfolio/DomesticForeignBar";
import DividendTab from "../components/portfolio/DividendTab";
import { fmtKrwPrice } from "../utils/format";
import { invalidateSyncData } from "../utils/queryInvalidation";
import { useRegisterRefresh } from "../hooks/useRegisterRefresh";
import { toast } from "../utils/toast";
import { pnlColor } from "../utils/colors";
import SkeletonCard from "../components/common/SkeletonCard";
import SkeletonStatBox from "../components/common/SkeletonStatBox";
import ErrorBoundary from "../components/ErrorBoundary";
import { DOMESTIC_MARKETS } from "../constants";
import { STALE_TIME, REFETCH_INTERVAL } from "../constants/queryConfig";
import { QUERY_KEYS } from "../constants/queryKeys";
import type { PortfolioOverview, DividendByTicker, DividendYield } from "../types";

interface DividendSummary {
  annual_received: number;
  estimated_annual: number;
  monthly_breakdown: { month: string; amount: number }[];
  monthly_ticker_breakdown: { month: string; ticker: string | null; amount: number }[];
}

const fetchOverview = () => api.get<PortfolioOverview>("/portfolio/overview").then((r) => r.data);

import { PORTFOLIO_TABS } from "../constants/tabs";
const TABS = PORTFOLIO_TABS;
type Tab = (typeof TABS)[number];

export default function PortfolioPage() {
  const qc = useQueryClient();

  const handleRefresh = useCallback(async () => {
    await invalidateSyncData(qc);
  }, [qc]);
  useRegisterRefresh(handleRefresh);

  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = TABS.includes(searchParams.get("tab") as Tab)
    ? (searchParams.get("tab") as Tab)
    : "종목 현황";
  const [tab, setTab] = useState<Tab>(initialTab);

  const handleTabChange = useCallback((next: Tab) => {
    setTab(next);
    setSearchParams({ tab: next }, { replace: true });
  }, [setSearchParams]);
  const [syncingAll, setSyncingAll] = useState(false);
  const [syncProgress, setSyncProgress] = useState({ done: 0, total: 0 });

  const { data, isLoading, error } = useQuery({
    queryKey: QUERY_KEYS.portfolioOverview,
    queryFn: fetchOverview,
    refetchInterval: REFETCH_INTERVAL.PORTFOLIO,
  });

  const { data: dividendData = [], isLoading: divLoading, isError: divError } = useQuery({
    queryKey: QUERY_KEYS.dividendPositions,
    queryFn: () => api.get<DividendYield[]>("/dividends/positions").then((r) => r.data),
    enabled: tab === "종목 현황" || tab === "배당 현황",
    staleTime: STALE_TIME.LONG,
  });

  const { data: divSummary } = useQuery({
    queryKey: QUERY_KEYS.dividendSummary,
    queryFn: () => api.get<DividendSummary>("/dividends/summary").then((r) => r.data),
    enabled: tab === "배당 현황",
    staleTime: STALE_TIME.LONG,
  });

  const { data: dividendByTicker = [] } = useQuery({
    queryKey: QUERY_KEYS.dividendByTicker,
    queryFn: () => api.get<DividendByTicker[]>("/dividends/by-ticker").then((r) => r.data),
    enabled: tab === "배당 현황",
    staleTime: STALE_TIME.LONG,
  });

  const handleSyncAll = async () => {
    if (!data) return;
    const accounts = data.accounts.filter(
      (a) => a.asset_type.startsWith("STOCK") || a.asset_type === "CASH_OTHER"
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
        })
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
    () => data?.accounts.filter((a) => a.asset_type.startsWith("STOCK") || a.asset_type === "CASH_OTHER") ?? [],
    [data]
  );

  const marketChartData = useMemo(() => {
    if (!data) return [];
    let domestic = 0;
    let foreign = 0;
    for (const p of data.all_positions) {
      if (DOMESTIC_MARKETS.includes(p.market)) domestic += p.value_krw;
      else foreign += p.value_krw;
    }
    const total = domestic + foreign;
    if (total === 0) return [];
    const items = [];
    if (domestic > 0) items.push({ name: "국내 주식", value: domestic, pct: (domestic / total) * 100 });
    if (foreign > 0) items.push({ name: "해외 주식", value: foreign, pct: (foreign / total) * 100 });
    return items;
  }, [data]);

  const stockChartData = useMemo(
    () => (data?.stock_allocation ?? []).map((a) => ({
      name: a.name,
      ticker: a.ticker,
      value: a.value_krw ?? 0,
      pct: a.pct,
    })),
    [data]
  );

  if (isLoading) return (
    <div className="space-y-6">
      <div className="card">
        <div className="grid grid-cols-2 gap-px bg-gray-100 dark:bg-gray-700 sm:flex sm:divide-x sm:divide-gray-100 sm:dark:divide-gray-700 sm:bg-transparent sm:gap-0">
          {[0, 1, 2, 3].map((i) => <SkeletonStatBox key={i} />)}
        </div>
      </div>
      <SkeletonCard rows={5} height="h-4" />
      <SkeletonCard rows={3} height="h-4" />
    </div>
  );
  if (error || !data) return (
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
            {syncingAll
              ? `${syncProgress.done}/${syncProgress.total} 갱신 중...`
              : "전체 갱신"}
          </button>
          <span className="text-xs text-gray-400 dark:text-gray-500">{stockAccounts.length}개 증권사 계좌</span>
        </div>
      </div>

      {/* 상단 요약 */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-3 sm:p-5">
        <p className="text-xs tracking-wide uppercase font-semibold text-gray-400 dark:text-gray-500">주식 총평가액</p>
        <p className="text-2xl sm:text-3xl font-bold mt-1 leading-tight text-blue-600">
          {fmtKrwPrice(data.total_stock_krw)}
        </p>
        <div className="mt-2">
          <span className={`text-sm font-semibold ${pnlColor(data.unrealized_pnl_krw)}`}>
            평가손익 {data.unrealized_pnl_krw >= 0 ? "+" : ""}{fmtKrwPrice(data.unrealized_pnl_krw)}({data.stock_return_pct >= 0 ? "+" : ""}{data.stock_return_pct.toFixed(2)}%)
          </span>
        </div>
      </div>

      {/* 탭 */}
      <Tabs tabs={TABS} activeTab={tab} onChange={handleTabChange} variant="pill" />

      {tab === "종목 현황" && (
        <ErrorBoundary variant="section">
          <DomesticForeignBar items={marketChartData} />
          <TreemapChart data={stockChartData} title="종목별 비중" />
          {(() => {
            const dividendMap = Object.fromEntries(
              dividendData.map((d) => [`${d.ticker}-${d.market}`, d])
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

      {tab === "배당 현황" && (
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

      {tab === "포트폴리오 분석" && (
        <ErrorBoundary variant="section">
          <PortfolioAnalysisTab />
        </ErrorBoundary>
      )}
    </div>
  );
}
