import { useMemo } from "react";
import { TrendingDown, TrendingUp } from "lucide-react";
import { fmtKrw, fmtMonth, fmtPct } from "../../utils/format";
import { pnlColor, PROFIT_COLOR, LOSS_COLOR } from "../../utils/colors";
import { ASSET_TYPE_LABELS } from "../../constants";
import AssetAllocationChart from "./AssetAllocationChart";
import type { DashboardData } from "../../api/dashboard";
import type { DCAAnalysisData } from "../../api/invest";

interface Props {
  data: DashboardData;
  dcaData: DCAAnalysisData | undefined;
  exchangeRate: number | null;
}

export default function HeroSummaryCard({ data, dcaData, exchangeRate }: Props) {
  const currentYear = new Date().getFullYear();

  const allocationChartData = useMemo(() => {
    const CASH_TYPES = new Set(["BANK_ACCOUNT", "DEPOSIT", "CASH_OTHER", "CASH_STOCK"]);
    const stockItems = data.asset_allocation.filter((item) => item.type.startsWith("STOCK_"));
    const cashItems = data.asset_allocation.filter((item) => CASH_TYPES.has(item.type));
    const otherItems = data.asset_allocation.filter(
      (item) => !item.type.startsWith("STOCK_") && !CASH_TYPES.has(item.type)
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
  }, [data.asset_allocation]);

  const depositColor =
    data.deposit_achievement_pct != null && data.deposit_achievement_pct >= 100
      ? "text-green-600"
      : "text-blue-600 dark:text-blue-400";

  const timeline = dcaData?.goal_timeline;
  const currentProgressPct = timeline?.current_progress_pct ?? data.goal_achievement_pct;
  const progressColor =
    currentProgressPct == null
      ? "text-gray-400 dark:text-gray-500"
      : currentProgressPct >= 100
      ? "text-red-500"
      : currentProgressPct >= 80
      ? "text-orange-500"
      : "text-gray-600 dark:text-gray-300";

  const goalAmountDisplay = dcaData?.settings.goal_amount ?? data.goal_amount;

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 flex flex-col gap-3 lg:gap-4">
      <div className="flex flex-row gap-3 lg:gap-6">
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
            </div>
            <div className="grid grid-cols-2 gap-2 sm:gap-4">
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">누적 수익률</p>
                <p className={`text-lg sm:text-xl font-bold mt-0.5 ${
                  data.cumulative_return_pct == null
                    ? "text-gray-400 dark:text-gray-500"
                    : pnlColor(data.cumulative_return_pct)
                }`}>
                  {fmtPct(data.cumulative_return_pct)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">환율(USD/KRW)</p>
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-200 mt-0.5">
                  {exchangeRate ? Math.round(exchangeRate).toLocaleString() + "원" : "—"}
                </p>
              </div>
            </div>
          </div>
          {/* 보조 항목: 입금 달성률 · 은퇴 목표 */}
          <div className="border-t border-gray-100 dark:border-gray-700 mt-4 pt-4">
            <div className="grid grid-cols-2 gap-2 sm:gap-4">
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500 font-medium truncate">입금 달성률</p>
                <p className={`text-sm font-semibold mt-0.5 ${depositColor}`}>
                  {data.deposit_achievement_pct != null ? `${data.deposit_achievement_pct.toFixed(1)}%` : "목표 미설정"}
                </p>
                {data.annual_deposit_goal != null && (
                  <p className="text-xs text-gray-300 dark:text-gray-600 truncate mt-0.5">목표 {fmtKrw(data.annual_deposit_goal)}</p>
                )}
              </div>
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">은퇴 목표</p>
                {data.retirement_target_year ? (
                  <>
                    <p className="text-sm font-semibold text-blue-600 dark:text-blue-400 mt-0.5">
                      {data.retirement_target_year}년
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      {data.retirement_target_year - currentYear}년 후
                    </p>
                  </>
                ) : (
                  <p className="text-sm font-semibold text-blue-600 dark:text-blue-400 mt-0.5">미설정</p>
                )}
              </div>
            </div>
          </div>
        </div>
        {/* 모바일: 확대된 compact 도넛 차트 (우측 고정) */}
        <div className="lg:hidden w-36 sm:w-44 shrink-0">
          {allocationChartData.length > 0 ? (
            <AssetAllocationChart data={allocationChartData} size="compact" />
          ) : (
            <div className="flex items-center justify-center h-44 text-gray-300 dark:text-gray-600 text-xs text-center">
              자산<br />없음
            </div>
          )}
        </div>
        {/* 데스크탑: 풀사이즈 도넛 차트 */}
        <div className="hidden lg:block lg:w-[460px] shrink-0">
          {allocationChartData.length > 0 ? (
            <AssetAllocationChart data={allocationChartData} />
          ) : (
            <div className="flex items-center justify-center h-40 text-gray-300 dark:text-gray-600 text-sm">
              자산 데이터 없음
            </div>
          )}
        </div>
      </div>
      {/* 목표 달성 전망 */}
      <div className="border-t border-gray-100 dark:border-gray-700 pt-3 space-y-3">
        <div className="grid grid-cols-3 gap-2 sm:gap-4">
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">현재 진행율</p>
            <p className={`text-sm sm:text-base lg:text-lg font-bold ${progressColor}`}>
              {currentProgressPct != null ? `${currentProgressPct.toFixed(1)}%` : "—"}
            </p>
            {goalAmountDisplay != null && (
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">목표 {fmtKrw(goalAmountDisplay)}</p>
            )}
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">목표 달성 예상</p>
            <p className="text-sm sm:text-base lg:text-lg font-bold text-gray-900 dark:text-gray-50">
              {timeline?.expected_goal_date ? fmtMonth(timeline.expected_goal_date) : "—"}
            </p>
            {timeline?.months_to_goal != null && (
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">약 {timeline.months_to_goal}개월 후</p>
            )}
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">계획 대비</p>
            {timeline?.lead_lag_months == null ? (
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">—</p>
            ) : timeline.lead_lag_months > 0 ? (
              <span className="flex flex-col gap-0.5 mt-1">
                <span className={`text-xs font-medium ${PROFIT_COLOR} flex items-center gap-1`}>
                  <TrendingUp size={12} />{timeline.lead_lag_months}개월 앞서
                </span>
                {timeline.actual_expected_goal_date && (
                  <span className="text-xs text-red-400 whitespace-nowrap">{fmtMonth(timeline.actual_expected_goal_date)} 달성 예상</span>
                )}
              </span>
            ) : timeline.lead_lag_months < 0 ? (
              <span className="flex flex-col gap-0.5 mt-1">
                <span className={`text-xs font-medium ${LOSS_COLOR} flex items-center gap-1`}>
                  <TrendingDown size={12} />{Math.abs(timeline.lead_lag_months)}개월 지연
                </span>
                {timeline.actual_expected_goal_date && (
                  <span className="text-xs text-blue-400 whitespace-nowrap">{fmtMonth(timeline.actual_expected_goal_date)} 달성 예상</span>
                )}
              </span>
            ) : (
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mt-1">계획과 일치</p>
            )}
          </div>
        </div>
        {currentProgressPct != null && (
          <div>
            <div className="flex justify-between text-xs text-gray-400 dark:text-gray-500 mb-1">
              <span>0%</span>
              <span>100%</span>
            </div>
            <div className="h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all"
                style={{ width: `${Math.min(currentProgressPct, 100)}%` }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
