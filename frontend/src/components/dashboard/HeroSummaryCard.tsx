import { memo, useMemo } from "react";
import { RefreshCw } from "lucide-react";
import { fmtKrw, fmtKrwShort, fmtPct } from "@/utils/format";
import { pnlColor, PIE_COLORS } from "@/utils/colors";
import { ASSET_TYPE_LABELS } from "@/constants";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import type { DashboardData } from "@/api/dashboard";
import MiniDonut from "@/components/common/MiniDonut";

const CASH_TYPES = new Set(["BANK_ACCOUNT", "DEPOSIT", "CASH_OTHER", "CASH_STOCK"]);
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
    // 실제 카드 모양(좌: 제목·총액·지표 / 우: 도넛)에 맞춘 스켈레톤
    return (
      <div className="card">
        <div
          role="status"
          aria-label="로딩 중"
          aria-busy="true"
          className="flex items-center gap-4 animate-pulse"
        >
          <div className="flex-1 space-y-2">
            <div className="h-3 w-16 rounded bg-gray-200 dark:bg-gray-700" />
            <div className="h-7 w-32 rounded bg-gray-200 dark:bg-gray-700" />
            <div className="h-4 w-40 rounded bg-gray-200 dark:bg-gray-700" />
          </div>
          <div className="w-24 h-24 rounded-full bg-gray-200 dark:bg-gray-700 shrink-0" />
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      {/* 1행 [지표 | 도넛], 2행 [업데이트 시각 | 범례] — 범례는 항상 도넛 바로 아래 (docs/plans/67 P1-2) */}
      <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-2 sm:gap-x-4 items-center">
        {/* 좌: 제목/금액 + 지표 */}
        <div className="min-w-0 flex flex-col gap-1 sm:gap-2">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-xs text-gray-500 dark:text-gray-400 font-medium">전체 자산</h2>
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
          {/* 원 단위 전체 금액은 같은 값의 이중 표기라 title로만 제공(U1) */}
          <p
            className="text-2xl sm:text-3xl lg:text-4xl font-bold text-gray-900 dark:text-gray-50"
            title={`${Math.floor(data.total_assets_krw).toLocaleString()}원`}
          >
            {fmtKrw(Math.floor(data.total_assets_krw))}
          </p>
          <div className="grid grid-cols-2 gap-2 sm:gap-4 pt-1.5 sm:pt-2">
            <div>
              {/* 기준을 화면에 표시 — 주식 평가손익률(매입원가)·목표 연수익률(XIRR)과 구분 (67 P1-1) */}
              <p className="text-xs text-gray-500 dark:text-gray-400 font-medium">
                누적 수익률 <span className="font-normal">(전체 자산)</span>
              </p>
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
              <p className="text-xs text-gray-500 dark:text-gray-400 font-medium">환율(USD/KRW)</p>
              <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                {exchangeRate ? Math.round(exchangeRate).toLocaleString() + "원" : "—"}
              </p>
            </div>
          </div>
        </div>

        {/* 우: 도넛 */}
        <div className="w-32 h-32 sm:w-[180px] sm:h-44 lg:w-[196px] lg:h-48 xl:w-[208px]">
          {allocationChartData.length > 0 ? (
            <MiniDonut data={allocationChartData} />
          ) : (
            <div className="flex items-center justify-center w-full h-full text-gray-400 dark:text-gray-500 text-xs text-center">
              자산 데이터 없음
            </div>
          )}
        </div>

        {updatedLabel && (
          <p className="text-xs text-gray-400 dark:text-gray-500 sm:self-end">{updatedLabel}</p>
        )}

        {/* 범례: 비중만 표시 — 금액은 아래 카드(주식 투자 현황)·자산 탭과 중복이라 sm+에서만 (67 P1-2).
            모바일 max-w-40: 2항목은 한 줄, 그 이상은 도넛 폭 근처에서 줄바꿈(지표 열을 밀어내지 않게) */}
        {allocationChartData.length > 0 && (
          <ul className="col-start-2 justify-self-center max-w-40 flex flex-wrap justify-center gap-x-2 gap-y-1 sm:max-w-none sm:justify-self-stretch sm:grid sm:grid-cols-2 sm:gap-x-1.5 sm:gap-y-0.5">
            {allocationChartData.map((item, i) => (
              <li key={i} className="flex items-center gap-1 min-w-0">
                <span
                  className="inline-block w-2.5 h-2.5 rounded-sm shrink-0"
                  style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                />
                <span className="text-xs text-gray-600 dark:text-gray-400 leading-tight truncate min-w-0">
                  {item.name} {item.pct.toFixed(0)}%
                  <span className="hidden sm:inline text-gray-500 ml-0.5">
                    · {fmtKrwShort(item.value)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
});
