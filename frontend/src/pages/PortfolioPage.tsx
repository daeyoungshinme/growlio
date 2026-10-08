import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState, lazy, Suspense } from "react";
import { useSearchParams } from "react-router-dom";
import { RefreshCw, X } from "lucide-react";
import Tabs from "@/components/common/Tabs";
import { fetchAccounts, syncAccount, syncAllAccounts } from "@/api/assets";
import { useSyncStore } from "@/stores/syncStore";
import { useDividendData } from "@/hooks/useDividendData";
import StockHoldingsTable from "@/components/assets/StockHoldingsTable";
import HorizonSummaryCard from "@/components/dashboard/HorizonSummaryCard";
import DividendTab from "@/components/portfolio/DividendTab";
import { fmtKrw } from "@/utils/format";
import { invalidateSyncData } from "@/utils/queryInvalidation";
import { useRegisterRefresh } from "@/hooks/useRegisterRefresh";
import { useSwipeTabs } from "@/hooks/useSwipeNavigation";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { pnlColor } from "@/utils/colors";
import SkeletonCard from "@/components/common/SkeletonCard";
import SkeletonStatBox from "@/components/common/SkeletonStatBox";
import ErrorBoundary from "@/components/ErrorBoundary";
import { STALE_TIME, REFETCH_INTERVAL } from "@/constants/queryConfig";
import { isNativePlatform } from "@/utils/platform";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { PORTFOLIO_TABS } from "@/constants/tabs";
import {
  TOUCH_TARGET_MIN_MOBILE_ONLY,
  TOUCH_TARGET_COMPACT_MOBILE_ONLY,
} from "@/constants/uiSizes";
import { SELECT_SM } from "@/constants/inputStyles";
import { isPortfolioAccount, isStockAccount, isSyncableAccount } from "@/utils/accounts";
import { useQuery } from "@tanstack/react-query";
import { fetchPortfolioOverview } from "@/api/portfolios";

const AllocationCard = lazy(() => import("../components/portfolio/AllocationCard"));

const SYNC_BUTTON_CLASS = `${TOUCH_TARGET_MIN_MOBILE_ONLY} gap-1.5 px-3 py-1.5 text-sm border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-950 disabled:opacity-50 transition-colors`;
const TABS = PORTFOLIO_TABS;
type Tab = (typeof TABS)[number];

export default function PortfolioPage() {
  const qc = useQueryClient();

  const handleRefresh = useCallback(async () => {
    await invalidateSyncData(qc);
  }, [qc]);
  useRegisterRefresh(handleRefresh);

  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("portfolioTab");

  const tab: Tab = TABS.includes(rawTab as Tab) ? (rawTab as Tab) : "종목 현황";

  const handleTabChange = useCallback(
    (next: Tab) => {
      setSearchParams(
        (prev) => {
          prev.set("portfolioTab", next);
          return prev;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const selectedAccountId = searchParams.get("account") || null;

  const handleAccountChange = useCallback(
    (next: string) => {
      setSearchParams(
        (prev) => {
          if (next) prev.set("account", next);
          else prev.delete("account");
          return prev;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );
  const isSyncingAll = useSyncStore((s) => s.isSyncingAll);
  const syncDone = useSyncStore((s) => s.done);
  const syncTotal = useSyncStore((s) => s.total);
  const startSyncAll = useSyncStore((s) => s.startSyncAll);
  const failedAccounts = useSyncStore((s) => s.failedAccounts);
  const removeFailedAccount = useSyncStore((s) => s.removeFailedAccount);
  const dismissFailedAccounts = useSyncStore((s) => s.dismissFailedAccounts);
  const [retryingAccountId, setRetryingAccountId] = useState<string | null>(null);
  const [isSyncingSelected, setIsSyncingSelected] = useState(false);

  const tabContentRef = useRef<HTMLDivElement>(null);
  useSwipeTabs(tabContentRef, TABS, tab, handleTabChange);

  const { data: accountsList } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
    staleTime: STALE_TIME.LONG,
  });
  const accountOptions = useMemo(
    () => (accountsList ?? []).filter((a) => isStockAccount(a.asset_type)),
    [accountsList],
  );
  const selectedAccount = useMemo(
    () => accountOptions.find((a) => a.id === selectedAccountId) ?? null,
    [accountOptions, selectedAccountId],
  );
  const canSyncSelected = !!selectedAccount && isSyncableAccount(selectedAccount.data_source);

  const { data, isLoading, error } = useQuery({
    queryKey: QUERY_KEYS.portfolioOverview(selectedAccountId),
    queryFn: () => fetchPortfolioOverview(selectedAccountId),
    staleTime: STALE_TIME.EXCHANGE_RATE,
    refetchInterval: isNativePlatform() ? false : REFETCH_INTERVAL.PORTFOLIO,
  });

  const {
    dividendPositions: dividendData,
    dividendSummary: divSummary,
    dividendByTicker,
    isLoading: divLoading,
    isError: divError,
  } = useDividendData(!isLoading && !!data, selectedAccountId);

  const handleSyncAll = async () => {
    try {
      const { total } = await syncAllAccounts();
      startSyncAll(total);
    } catch (e) {
      toast(extractErrorMessage(e, "전체 동기화를 시작하지 못했습니다"), "error");
    }
  };

  const handleRetryFailedAccount = async (accountId: string) => {
    setRetryingAccountId(accountId);
    try {
      await syncAccount(accountId);
      await invalidateSyncData(qc);
      removeFailedAccount(accountId);
      toast("동기화 완료", "success");
    } catch (e) {
      toast(extractErrorMessage(e, "계좌 동기화에 실패했습니다"), "error");
    } finally {
      setRetryingAccountId(null);
    }
  };

  const handleSyncSelected = async () => {
    if (!selectedAccount) return;
    setIsSyncingSelected(true);
    try {
      await syncAccount(selectedAccount.id);
      await invalidateSyncData(qc);
      toast("동기화 완료", "success");
    } catch (e) {
      toast(extractErrorMessage(e, "계좌 동기화에 실패했습니다"), "error");
    } finally {
      setIsSyncingSelected(false);
    }
  };

  const stockAccounts = useMemo(
    () => data?.accounts.filter((a) => isPortfolioAccount(a.asset_type)) ?? [],
    [data],
  );

  if (isLoading)
    return (
      <div className="space-y-6">
        <div className="card">
          <div
            role="status"
            aria-label="로딩 중"
            aria-busy="true"
            className="grid grid-cols-2 gap-px bg-gray-100 dark:bg-gray-700 sm:flex sm:divide-x sm:divide-gray-100 sm:dark:divide-gray-700 sm:bg-transparent sm:gap-0"
          >
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
          onClick={() =>
            qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolioOverview(selectedAccountId) })
          }
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors`}
        >
          다시 시도
        </button>
      </div>
    );

  const hasHorizonTags = data.accounts.some((a) => a.investment_horizon);
  const pnlSign = data.unrealized_pnl_krw >= 0 ? "+" : "";
  const returnSign = data.stock_return_pct >= 0 ? "+" : "";
  const stockSharePct =
    data.total_assets_krw > 0 ? (data.total_stock_krw / data.total_assets_krw) * 100 : null;

  // 모바일은 좁은 헤더에 맞춰 짧은 라벨을 보이고, 접근 이름(aria-label)은 전체 문구를 유지한다.
  const syncAction = selectedAccount
    ? {
        onClick: handleSyncSelected,
        disabled: isSyncingSelected || !canSyncSelected,
        title: canSyncSelected ? undefined : "수동 계좌는 갱신할 수 없습니다",
        spinning: isSyncingSelected,
        label: isSyncingSelected ? "갱신 중..." : "선택 계좌 갱신",
        shortLabel: isSyncingSelected ? "갱신 중" : "갱신",
      }
    : {
        onClick: handleSyncAll,
        disabled: isSyncingAll,
        title: undefined,
        spinning: isSyncingAll,
        label: isSyncingAll ? `${syncDone}/${syncTotal} 갱신 중...` : "전체 갱신",
        shortLabel: isSyncingAll ? `${syncDone}/${syncTotal}` : "갱신",
      };

  return (
    <div className="space-y-6">
      {/* 상단 요약 */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-4 sm:p-5">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <p className="text-xs tracking-wide uppercase font-semibold text-gray-400 dark:text-gray-500">
            주식 총평가액
          </p>
          <div className="flex items-center gap-2 min-w-0">
            {accountOptions.length > 0 && (
              <select
                value={selectedAccountId ?? ""}
                onChange={(e) => handleAccountChange(e.target.value)}
                className={`${SELECT_SM} min-w-0 max-w-[10rem] sm:max-w-none truncate`}
                aria-label="계좌 선택"
              >
                <option value="">전체 계좌 ({stockAccounts.length}개)</option>
                {accountOptions.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            )}
            <button
              onClick={syncAction.onClick}
              disabled={syncAction.disabled}
              title={syncAction.title}
              aria-label={syncAction.label}
              className={`${SYNC_BUTTON_CLASS} shrink-0`}
            >
              <RefreshCw size={14} className={syncAction.spinning ? "animate-spin" : ""} />
              <span className="sm:hidden">{syncAction.shortLabel}</span>
              <span className="hidden sm:inline">{syncAction.label}</span>
            </button>
          </div>
        </div>
        <p className="text-2xl sm:text-3xl font-bold mt-1 leading-tight tabular-nums text-blue-600 dark:text-blue-400">
          {fmtKrw(data.total_stock_krw)}
        </p>
        <p
          className={`mt-2 text-sm font-semibold tabular-nums ${pnlColor(data.unrealized_pnl_krw)}`}
        >
          평가손익 <span>{`${pnlSign}${fmtKrw(data.unrealized_pnl_krw)}`}</span> (
          <span>{`${returnSign}${data.stock_return_pct.toFixed(2)}%`}</span>)
        </p>
        {(stockSharePct !== null || data.total_non_stock_krw > 0) && (
          <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">
            {[
              stockSharePct !== null && `전체 자산 중 ${stockSharePct.toFixed(1)}%`,
              data.total_non_stock_krw > 0 &&
                `현금·부동산 등 ${fmtKrw(data.total_non_stock_krw)} 별도`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        )}
        {/* 특정 계좌 선택 시 overview.accounts가 해당 계좌 1건으로 축소되어
            상단 "주식 총평가액"과 동일한 값만 나오므로 전체 계좌 뷰에서만 표시 */}
        {!selectedAccountId && hasHorizonTags && (
          <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
            <HorizonSummaryCard overview={data} />
          </div>
        )}
        {failedAccounts.length > 0 && !isSyncingAll && (
          <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
            <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950 p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium text-red-700 dark:text-red-400">
                  {failedAccounts.length}개 계좌 동기화 실패
                </p>
                <button
                  onClick={dismissFailedAccounts}
                  aria-label="닫기"
                  className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} -m-1 text-red-400 hover:text-red-600 dark:hover:text-red-300 rounded-lg transition-colors`}
                >
                  <X size={14} />
                </button>
              </div>
              <ul className="mt-2 space-y-1.5">
                {failedAccounts.map((a) => (
                  <li
                    key={a.account_id}
                    className="flex items-center justify-between gap-2 text-xs"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="font-medium text-gray-700 dark:text-gray-200">
                        {a.account_name}
                      </span>
                      <span className="block truncate text-red-600 dark:text-red-400">
                        {a.error}
                      </span>
                    </span>
                    <button
                      onClick={() => handleRetryFailedAccount(a.account_id)}
                      disabled={retryingAccountId === a.account_id}
                      className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} shrink-0 px-2 text-xs border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-100 dark:hover:bg-red-900 disabled:opacity-50 transition-colors`}
                    >
                      {retryingAccountId === a.account_id ? "재시도 중..." : "다시 시도"}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>

      {/* 탭 */}
      <div>
        {/* 상위 "투자현황/계좌관리"가 pill이라 하위 탭은 밑줄형으로 위계를 구분한다 */}
        <Tabs tabs={TABS} activeTab={tab} onChange={handleTabChange} variant="underline" />
      </div>

      <div ref={tabContentRef}>
        {tab === "종목 현황" && (
          <ErrorBoundary variant="section">
            <Suspense fallback={<SkeletonCard rows={3} height="h-10" />}>
              <AllocationCard overview={data} accountId={selectedAccountId} />
            </Suspense>
            {(() => {
              const dividendMap = Object.fromEntries(
                dividendData.map((d) => [`${d.ticker}-${d.market}`, d]),
              );
              return (
                <StockHoldingsTable
                  positions={data.all_positions}
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
      </div>
    </div>
  );
}
