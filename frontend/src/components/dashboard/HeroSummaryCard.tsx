import { lazy, memo, Suspense, useMemo } from "react";
import { fmtKrw, fmtPct } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { ASSET_TYPE_LABELS } from "@/constants";
import SkeletonStatBox from "@/components/common/SkeletonStatBox";
import type { DashboardData } from "@/api/dashboard";

const AssetAllocationChart = lazy(() => import("./AssetAllocationChart"));

const CASH_TYPES = new Set(["BANK_ACCOUNT", "DEPOSIT", "CASH_OTHER", "CASH_STOCK"]);

interface Props {
  data: DashboardData | undefined;
  exchangeRate: number | null;
  dataUpdatedAt?: number;
  isLoading?: boolean;
}

export default memo(function HeroSummaryCard({
  data,
  exchangeRate,
  dataUpdatedAt,
  isLoading,
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
    <div className="card flex flex-col gap-3 lg:gap-4">
      <div className="flex flex-row gap-3 lg:gap-6 items-start">
        {/* 좌측: 자산 총액 + 누적 수익률 + 보조 지표 */}
        <div className="flex-1 min-w-0 flex flex-col justify-between">
          <div className="flex flex-col gap-4">
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">전체 자산</p>
              <p className="text-2xl sm:text-3xl lg:text-4xl font-bold text-gray-900 dark:text-gray-50 mt-1">
                {fmtKrw(Math.floor(data.total_assets_krw))}
              </p>
              <p className="text-sm text-gray-400 dark:text-gray-500 mt-0.5">
                {Math.floor(data.total_assets_krw).toLocaleString()}원
              </p>
              {updatedLabel && (
                <p className="text-xs text-gray-300 dark:text-gray-600 mt-1">{updatedLabel}</p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3 sm:gap-4">
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">누적 수익률</p>
                <p
                  className={`text-lg sm:text-xl font-bold mt-0.5 ${
                    data.cumulative_return_pct == null
                      ? "text-gray-400 dark:text-gray-500"
                      : pnlColor(data.cumulative_return_pct)
                  }`}
                >
                  {fmtPct(data.cumulative_return_pct)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">
                  환율(USD/KRW)
                </p>
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-200 mt-0.5">
                  {exchangeRate ? Math.round(exchangeRate).toLocaleString() + "원" : "—"}
                </p>
              </div>
            </div>
          </div>
        </div>
        {/* 모바일: compact-sm 도넛 차트 (우측 고정) */}
        <div className="lg:hidden w-36 sm:w-44 shrink-0">
          {allocationChartData.length > 0 ? (
            <Suspense fallback={<div className="h-36" />}>
              <AssetAllocationChart data={allocationChartData} size="compact-sm" />
            </Suspense>
          ) : (
            <div className="flex items-center justify-center h-28 text-gray-300 dark:text-gray-600 text-xs text-center">
              자산
              <br />
              없음
            </div>
          )}
        </div>
        {/* 데스크탑: mobile 사이즈 도넛 차트 */}
        <div className="hidden lg:block lg:w-80 xl:w-96 shrink-0">
          {allocationChartData.length > 0 ? (
            <Suspense fallback={<div className="h-56" />}>
              <AssetAllocationChart data={allocationChartData} size="mobile" />
            </Suspense>
          ) : (
            <div className="flex items-center justify-center h-40 text-gray-300 dark:text-gray-600 text-sm">
              자산 데이터 없음
            </div>
          )}
        </div>
      </div>
    </div>
  );
});
