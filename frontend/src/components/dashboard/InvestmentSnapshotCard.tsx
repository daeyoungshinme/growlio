import { Link } from "react-router-dom";
import { ArrowRight, TrendingUp } from "lucide-react";
import { fmtKrwShort } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { useCollapsible } from "@/hooks/useCollapsible";
import { useTaxLimitsSummary } from "@/hooks/useTaxLimitsSummary";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import HorizonSummaryCard from "@/components/dashboard/HorizonSummaryCard";
import TaxLimitsBanner from "@/components/dashboard/TaxLimitsBanner";
import type { PortfolioOverview } from "@/types";
import type { DashboardData } from "@/api/dashboard";

interface Props {
  overview: PortfolioOverview | undefined;
  data: DashboardData | undefined;
}

export default function InvestmentSnapshotCard({ overview, data }: Props) {
  const [isOpen, toggleOpen] = useCollapsible(true, "growlio:dashboard:investmentSnapshotOpen");
  const { parts: taxParts, warningText: taxWarningText } = useTaxLimitsSummary(overview);

  if (!overview || !overview.total_stock_krw || overview.total_stock_krw <= 0) return null;

  const pnl = overview.unrealized_pnl_krw;
  const pnlPct = overview.stock_return_pct;
  const hasDividend =
    data?.estimated_annual_dividends != null && data.estimated_annual_dividends > 0;
  const hasHorizonTags = overview.accounts.some((a) => a.investment_horizon);

  const collapsedHint = taxParts[0]
    ? `평가액 ${fmtKrwShort(overview.total_stock_krw)}원 · ${taxParts[0]}`
    : `평가액 ${fmtKrwShort(overview.total_stock_krw)}원`;

  return (
    <CollapsibleCard
      icon={TrendingUp}
      iconWrapClassName="bg-blue-50 dark:bg-blue-950"
      iconColorClassName="text-blue-600 dark:text-blue-400"
      title="주식 투자 현황"
      titleBadge={
        taxWarningText && (
          <span
            className="text-xs font-semibold bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 rounded-full px-2 py-0.5 shrink-0"
            aria-label={taxWarningText}
          >
            주의
          </span>
        )
      }
      headerRight={
        <Link
          to="/assets?tab=투자현황"
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          자세히 보기
        </Link>
      }
      isOpen={isOpen}
      onToggle={toggleOpen}
      collapsedHint={collapsedHint}
    >
      {/* 평가액 / 투자원금 / 평가손익 */}
      <div className="grid grid-cols-3 gap-2 sm:gap-4">
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">평가액</p>
          <p className="text-sm sm:text-base font-semibold text-gray-900 dark:text-gray-50 tabular-nums">
            {fmtKrwShort(overview.total_stock_krw)}원
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
            {Math.floor(overview.total_stock_krw).toLocaleString()}
          </p>
        </div>

        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">투자원금</p>
          <p className="text-sm sm:text-base font-semibold text-gray-900 dark:text-gray-50 tabular-nums">
            {fmtKrwShort(overview.total_invested_krw)}원
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
            {Math.floor(overview.total_invested_krw).toLocaleString()}
          </p>
        </div>

        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">
            평가손익 <span className="text-gray-400 dark:text-gray-500">(매입원가)</span>
          </p>
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

      {/* 투자기간별 자산현황 */}
      {hasHorizonTags && (
        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
          <HorizonSummaryCard overview={overview} embedded />
        </div>
      )}

      {/* 배당 현황 */}
      {hasDividend && (
        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 dark:text-gray-500">올해 수령</span>
            <span className="text-xs font-semibold text-gray-800 dark:text-gray-200 tabular-nums">
              {data?.annual_dividends_received
                ? fmtKrwShort(data.annual_dividends_received) + "원"
                : "—"}
            </span>
          </div>
          <div className="w-px h-3 bg-gray-200 dark:bg-gray-600" />
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 dark:text-gray-500">예상 연간</span>
            <span className="text-xs font-semibold text-gray-800 dark:text-gray-200 tabular-nums">
              {fmtKrwShort(data!.estimated_annual_dividends!)}원
            </span>
          </div>
          <Link
            to="/assets?tab=투자현황&portfolioTab=배당"
            className="ml-auto flex items-center gap-1 text-xs text-blue-500 dark:text-blue-400 hover:underline"
          >
            배당 상세 <ArrowRight size={11} />
          </Link>
        </div>
      )}

      {/* 세금 한도 요약 (ISA 만기/연금 공제한도/예상세금) — 니치 정보라 하단 배치, 상세는 자산탭 세금 서브탭 참고 */}
      {(taxParts.length > 0 || taxWarningText) && (
        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
          <TaxLimitsBanner overview={overview} />
        </div>
      )}
    </CollapsibleCard>
  );
}
