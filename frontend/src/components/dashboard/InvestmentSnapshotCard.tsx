import { Link } from "react-router-dom";
import { TrendingUp } from "lucide-react";
import { fmtKrwShort } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { useCollapsible } from "@/hooks/useCollapsible";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import type { PortfolioOverview } from "@/types";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";

interface Props {
  overview: PortfolioOverview | undefined;
}

export default function InvestmentSnapshotCard({ overview }: Props) {
  const [isOpen, toggleOpen] = useCollapsible(true, "growlio:dashboard:investmentSnapshotOpen");

  if (!overview || !overview.total_stock_krw || overview.total_stock_krw <= 0) return null;

  const pnl = overview.unrealized_pnl_krw;
  const pnlPct = overview.stock_return_pct;

  // 세금 한도·경고는 홈 "지금 할 일"(ActionItemsCard)과 계획 › 절세 탭으로 이동했다 (docs/plans/50 M5)
  const collapsedHint = `평가액 ${fmtKrwShort(overview.total_stock_krw)}원`;

  return (
    <CollapsibleCard
      icon={TrendingUp}
      iconWrapClassName="bg-blue-50 dark:bg-blue-950"
      iconColorClassName="text-blue-600 dark:text-blue-400"
      title="주식 투자 현황"
      headerRight={
        <Link
          to="/assets?tab=투자현황"
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} text-xs text-blue-600 dark:text-blue-400 hover:underline`}
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
          <p
            className="text-sm sm:text-base font-semibold text-gray-900 dark:text-gray-50 tabular-nums"
            title={`${Math.floor(overview.total_stock_krw).toLocaleString()}원`}
          >
            {fmtKrwShort(overview.total_stock_krw)}원
          </p>
        </div>

        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">투자원금</p>
          <p
            className="text-sm sm:text-base font-semibold text-gray-900 dark:text-gray-50 tabular-nums"
            title={`${Math.floor(overview.total_invested_krw).toLocaleString()}원`}
          >
            {fmtKrwShort(overview.total_invested_krw)}원
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
            title={`${pnl >= 0 ? "+" : ""}${Math.floor(pnl).toLocaleString()}원`}
          >
            {pnl >= 0 ? "+" : ""}
            {fmtKrwShort(pnl)}원
            <span className="text-xs font-normal ml-1">
              ({pnlPct >= 0 ? "+" : ""}
              {pnlPct.toFixed(1)}%)
            </span>
          </p>
        </div>
      </div>
    </CollapsibleCard>
  );
}
