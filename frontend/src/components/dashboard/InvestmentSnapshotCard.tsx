import { Link } from "react-router-dom";
import { TrendingUp } from "lucide-react";
import { fmtKrwShort } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import type { PortfolioOverview } from "@/types";
import type { DashboardData } from "@/api/dashboard";

interface Props {
  overview: PortfolioOverview | undefined;
  data: DashboardData | undefined;
}

export default function InvestmentSnapshotCard({ overview, data }: Props) {
  if (!overview || !overview.total_stock_krw || overview.total_stock_krw <= 0) return null;

  const pnl = overview.unrealized_pnl_krw;
  const pnlPct = overview.stock_return_pct;
  const hasDividend =
    data?.estimated_annual_dividends != null && data.estimated_annual_dividends > 0;

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 flex items-center gap-1.5">
          <TrendingUp size={16} className="text-blue-500" />
          주식 투자 현황
        </h2>
        <Link
          to="/assets?tab=투자현황"
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          자세히 보기
        </Link>
      </div>

      {/* 평가액 / 투자원금 / 평가손익 */}
      <div className="grid grid-cols-3 gap-2 sm:gap-4">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">평가액</p>
          <p className="text-sm sm:text-base font-semibold text-gray-900 dark:text-gray-50 tabular-nums">
            {fmtKrwShort(overview.total_stock_krw)}원
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
            {Math.floor(overview.total_stock_krw).toLocaleString()}
          </p>
        </div>

        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">투자원금</p>
          <p className="text-sm sm:text-base font-semibold text-gray-900 dark:text-gray-50 tabular-nums">
            {fmtKrwShort(overview.total_invested_krw)}원
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
            {Math.floor(overview.total_invested_krw).toLocaleString()}
          </p>
        </div>

        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">평가손익</p>
          <p
            className={`text-sm sm:text-base font-semibold tabular-nums ${
              pnl === 0 ? "text-gray-400 dark:text-gray-500" : pnlColor(pnl)
            }`}
          >
            {pnl >= 0 ? "+" : ""}
            {fmtKrwShort(pnl)}원
            <span className="text-xs font-normal ml-1">
              ({pnlPct >= 0 ? "+" : ""}
              {pnlPct.toFixed(1)}%)
            </span>
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
            {pnl >= 0 ? "+" : ""}
            {Math.floor(pnl).toLocaleString()}
          </p>
        </div>
      </div>

      {/* 배당 현황 */}
      {hasDividend && (
        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400">올해 수령</span>
            <span className="text-xs font-semibold text-gray-800 dark:text-gray-200 tabular-nums">
              {data?.annual_dividends_received
                ? fmtKrwShort(data.annual_dividends_received) + "원"
                : "—"}
            </span>
          </div>
          <div className="w-px h-3 bg-gray-200 dark:bg-gray-600" />
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400">예상 연간</span>
            <span className="text-xs font-semibold text-gray-800 dark:text-gray-200 tabular-nums">
              {fmtKrwShort(data!.estimated_annual_dividends!)}원
            </span>
          </div>
          <Link
            to="/assets?tab=투자현황&portfolioTab=배당"
            className="ml-auto text-xs text-blue-500 dark:text-blue-400 hover:underline"
          >
            배당 상세 →
          </Link>
        </div>
      )}
    </div>
  );
}
