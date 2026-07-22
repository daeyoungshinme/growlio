import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Anchor, X } from "lucide-react";
import { fetchPortfolios } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { useCollapsible } from "@/hooks/useCollapsible";

export default function SetupTargetPortfolioBanner() {
  const [dismissed, , setDismissed] = useCollapsible(
    false,
    "growlio:dashboard:target-portfolio-banner-dismissed",
  );
  const { data: portfolios } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
  });

  if (dismissed || !portfolios || portfolios.length > 0) return null;

  return (
    <div
      role="status"
      className="flex items-center gap-2 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-2xl px-4 py-2.5"
    >
      <div className="p-1.5 rounded-lg shrink-0 bg-blue-100/60 dark:bg-blue-900/40">
        <Anchor size={16} className="text-blue-500 dark:text-blue-400" aria-hidden="true" />
      </div>
      <p className="flex-1 min-w-0 text-sm font-medium text-blue-900 dark:text-blue-200 truncate">
        전체 투자 자산에 대한 기준 포트폴리오를 만들어보세요
      </p>
      <Link
        to="/rebalancing?rtab=포트폴리오"
        className="shrink-0 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline"
      >
        만들기 →
      </Link>
      <button
        onClick={() => setDismissed(true)}
        aria-label="배너 닫기"
        className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} shrink-0 -m-1 text-blue-400 hover:text-blue-600 dark:hover:text-blue-300`}
      >
        <X size={16} />
      </button>
    </div>
  );
}
