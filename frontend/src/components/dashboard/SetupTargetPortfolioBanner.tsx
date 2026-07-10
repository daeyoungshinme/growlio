import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Target, X } from "lucide-react";
import { fetchPortfolios } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";

export default function SetupTargetPortfolioBanner() {
  const [dismissed, setDismissed] = useState(false);
  const { data: portfolios } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
  });

  if (dismissed || !portfolios || portfolios.length > 0) return null;

  return (
    <div
      role="status"
      className="flex items-start gap-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-2xl p-4"
    >
      <Target
        size={20}
        className="mt-0.5 shrink-0 text-blue-500 dark:text-blue-400"
        aria-hidden="true"
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-blue-900 dark:text-blue-200">
          전체 투자 자산에 대한 목표 포트폴리오를 만들어보세요
        </p>
        <p className="text-xs text-blue-700 dark:text-blue-400 mt-0.5">
          계좌를 선택하지 않으면 전체 투자 자산을 기준으로 목표 비중과 리밸런싱을 관리할 수
          있습니다.
        </p>
      </div>
      <Link
        to="/rebalancing?rtab=포트폴리오"
        className="shrink-0 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline"
      >
        만들기 →
      </Link>
      <button
        onClick={() => setDismissed(true)}
        aria-label="배너 닫기"
        className="shrink-0 p-1 -m-1 text-blue-400 hover:text-blue-600 dark:hover:text-blue-300"
      >
        <X size={16} />
      </button>
    </div>
  );
}
