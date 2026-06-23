import { lazy, memo, Suspense, useMemo, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
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
  const [expanded, setExpanded] = useState(true);

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
      {/* 헤더: 총 자산 요약 + 접기/펼침 토글 */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">전체 자산</p>
          <p className="text-2xl sm:text-3xl lg:text-4xl font-bold text-gray-900 dark:text-gray-50 mt-0.5">
            {fmtKrw(Math.floor(data.total_assets_krw))}
          </p>
          {!expanded && (
            <div className="flex items-center gap-3 mt-1">
              <span
                className={`text-sm font-semibold ${
                  data.cumulative_return_pct == null
                    ? "text-gray-400 dark:text-gray-500"
                    : pnlColor(data.cumulative_return_pct)
                }`}
              >
                {fmtPct(data.cumulative_return_pct)}
              </span>
              {data.stock_return_pct !== 0 && (
                <span className="text-xs text-gray-400 dark:text-gray-500">
                  주식 {fmtPct(data.stock_return_pct)}
                </span>
              )}
              {updatedLabel && (
                <span className="text-xs text-gray-300 dark:text-gray-600">{updatedLabel}</span>
              )}
            </div>
          )}
        </div>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors shrink-0 mt-1"
          aria-label={expanded ? "카드 접기" : "카드 펼치기"}
          aria-expanded={expanded}
        >
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      {/* 펼침 상태: 상세 정보 */}
      {expanded && (
        <div className="flex flex-row gap-3 lg:gap-6 items-start">
          {/* 좌측: 수익률 지표 */}
          <div className="flex-1 min-w-0 flex flex-col gap-4">
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
                <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">주식 수익률</p>
                <p
                  className={`text-lg sm:text-xl font-bold mt-0.5 ${
                    data.stock_return_pct === 0
                      ? "text-gray-400 dark:text-gray-500"
                      : pnlColor(data.stock_return_pct)
                  }`}
                >
                  {data.stock_return_pct === 0 ? "—" : fmtPct(data.stock_return_pct)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">
                  {data.annual_return_pct != null ? "연간 수익률" : "누적 수익률"}
                </p>
                <p
                  className={`text-sm font-semibold mt-0.5 ${
                    (data.annual_return_pct ?? data.cumulative_return_pct) == null
                      ? "text-gray-400 dark:text-gray-500"
                      : pnlColor((data.annual_return_pct ?? data.cumulative_return_pct)!)
                  }`}
                >
                  {fmtPct(data.annual_return_pct ?? data.cumulative_return_pct)}
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
            {/* 자산 구성 요약 목록 */}
            {allocationChartData.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {allocationChartData.map((item) => (
                  <span
                    key={item.name}
                    className="text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-md px-2 py-0.5"
                  >
                    {item.name} {item.pct.toFixed(1)}%
                  </span>
                ))}
              </div>
            )}
            {updatedLabel && (
              <p className="text-xs text-gray-300 dark:text-gray-600">{updatedLabel}</p>
            )}
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
      )}
    </div>
  );
});
