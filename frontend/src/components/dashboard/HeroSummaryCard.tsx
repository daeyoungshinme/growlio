import { lazy, memo, Suspense, useMemo } from "react";
import { RefreshCw } from "lucide-react";
import { fmtKrw, fmtKrwShort, fmtPct } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { ASSET_TYPE_LABELS } from "@/constants";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import SkeletonStatBox from "@/components/common/SkeletonStatBox";
import type { DashboardData } from "@/api/dashboard";

const AssetAllocationChart = lazy(() => import("./AssetAllocationChart"));

const CASH_TYPES = new Set(["BANK_ACCOUNT", "DEPOSIT", "CASH_OTHER", "CASH_STOCK"]);
const CHART_COLORS = ["#2563EB", "#16A34A", "#D97706", "#DC2626", "#7C3AED", "#0891B2"];

interface Props {
  data: DashboardData | undefined;
  exchangeRate: number | null;
  dataUpdatedAt?: number;
  isLoading?: boolean;
  onSync?: () => void;
  syncing?: boolean;
}

export default memo(function HeroSummaryCard({
  data,
  exchangeRate,
  dataUpdatedAt,
  isLoading,
  onSync,
  syncing,
}: Props) {
  const updatedLabel = useMemo(() => {
    if (!dataUpdatedAt) return null;
    const mins = Math.floor((Date.now() - dataUpdatedAt) / 60_000);
    if (mins < 1) return "방금 업데이트";
    if (mins < 60) return `${mins}분 전 업데이트`;
    return `${Math.floor(mins / 60)}시간 전 업데이트`;
  }, [dataUpdatedAt]);

  const allocationChartData = useMemo(() => {
    if (!data) return [];
    const stockItems = data.asset_allocation.filter((item) => item.type.startsWith("STOCK_"));
    const cashItems = data.asset_allocation.filter((item) => CASH_TYPES.has(item.type));
    const otherItems = data.asset_allocation.filter(
      (item) => !item.type.startsWith("STOCK_") && !CASH_TYPES.has(item.type),
    );
    const result = otherItems.map((item) => ({
      name: ASSET_TYPE_LABELS[item.type] ?? item.type,
      value: item.amount_krw,
      pct: item.pct,
    }));
    if (cashItems.length > 0) {
      result.unshift({
        name: "현금",
        value: cashItems.reduce((sum, item) => sum + item.amount_krw, 0),
        pct: cashItems.reduce((sum, item) => sum + item.pct, 0),
      });
    }
    if (stockItems.length > 0) {
      result.unshift({
        name: "주식",
        value: stockItems.reduce((sum, item) => sum + item.amount_krw, 0),
        pct: stockItems.reduce((sum, item) => sum + item.pct, 0),
      });
    }
    return result;
  }, [data]);

  if (isLoading || !data) {
    return (
      <div className="card">
        <div className="grid grid-cols-2 gap-px bg-gray-100 dark:bg-gray-700 sm:flex sm:divide-x sm:divide-gray-100 sm:dark:divide-gray-700 sm:bg-transparent sm:gap-0">
          {[0, 1, 2, 3].map((i) => (
            <SkeletonStatBox key={i} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="card !pt-0 !pr-2 !pb-3 !pl-3 sm:!pt-0 sm:!pr-3 sm:!pb-5 sm:!pl-5 flex flex-col gap-3 lg:gap-4">
      <div className="flex flex-row items-center sm:gap-4">
        {/* 좌: 제목/금액 + 지표 */}
        <div className="flex-1 min-w-0 flex flex-col gap-1 sm:gap-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">전체 자산</p>
            <div className="flex items-center gap-1">
              {onSync && (
                <button
                  onClick={onSync}
                  disabled={syncing}
                  className={`lg:hidden -m-1 text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50 ${TOUCH_TARGET_MIN_MOBILE_ONLY}`}
                  aria-label="데이터 갱신"
                >
                  <RefreshCw size={15} className={syncing ? "animate-spin" : ""} />
                </button>
              )}
            </div>
          </div>
          <p className="text-2xl sm:text-3xl lg:text-4xl font-bold text-gray-900 dark:text-gray-50">
            {fmtKrw(Math.floor(data.total_assets_krw))}
          </p>
          <p className="text-sm text-gray-400 dark:text-gray-500 truncate">
            {Math.floor(data.total_assets_krw).toLocaleString()}원
          </p>
          <div className="grid grid-cols-2 gap-2 sm:gap-4 pt-1.5 sm:pt-2">
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">누적 수익률</p>
              <p
                className={`text-sm sm:text-lg font-bold ${
                  data.cumulative_return_pct == null
                    ? "text-gray-400 dark:text-gray-500"
                    : pnlColor(data.cumulative_return_pct)
                }`}
              >
                {fmtPct(data.cumulative_return_pct)}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">환율(USD/KRW)</p>
              <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                {exchangeRate ? Math.round(exchangeRate).toLocaleString() + "원" : "—"}
              </p>
            </div>
          </div>
          {updatedLabel && (
            <p className="text-xs text-gray-300 dark:text-gray-600">{updatedLabel}</p>
          )}
        </div>

        {/* 우: 도넛 + 범례 */}
        <div className="shrink-0 self-start w-[164px] sm:w-[180px] lg:w-[196px] xl:w-[208px] flex flex-col items-center gap-0 -mr-2 sm:mr-0">
          {allocationChartData.length > 0 ? (
            <Suspense fallback={<div className="w-full h-40 sm:h-44 lg:h-48" />}>
              <>
                <div className="w-full h-40 sm:h-44 lg:h-48">
                  <AssetAllocationChart
                    data={allocationChartData}
                    size="compact"
                    fillHeight={true}
                    showLegend={false}
                  />
                </div>
                <div className="grid grid-cols-2 gap-x-1.5 gap-y-0.5 w-full">
                  {allocationChartData.map((item, i) => (
                    <div key={i} className="flex items-center gap-1 min-w-0 w-full">
                      <span
                        className="inline-block w-2.5 h-2.5 rounded-sm shrink-0"
                        style={{ backgroundColor: CHART_COLORS[i % CHART_COLORS.length] }}
                      />
                      <span className="text-xs text-gray-500 dark:text-gray-400 leading-tight truncate min-w-0">
                        {item.name} {item.pct.toFixed(0)}%
                        <span className="text-gray-400 dark:text-gray-500 ml-0.5">
                          · {fmtKrwShort(item.value)}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              </>
            </Suspense>
          ) : (
            <div className="flex items-center justify-center w-full h-40 sm:h-44 lg:h-48 text-gray-300 dark:text-gray-600 text-xs text-center">
              자산 데이터 없음
            </div>
          )}
        </div>
      </div>
    </div>
  );
});
