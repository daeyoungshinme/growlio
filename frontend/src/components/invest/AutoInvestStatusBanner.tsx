import { ArrowRight, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchPortfolios } from "@/api/portfolios";
import { fetchRebalancingAlerts } from "@/api/alerts";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { mergeAlertsByPortfolio } from "@/utils/portfolio";
import { describeDcaAutoBuy, isDcaAutoBuyPreset } from "@/utils/dcaAutoBuy";

/** "정기 적립식 자동매수"(리밸런싱 AUTO의 SCHEDULE_ONLY+BUY_ONLY 프리셋) 설정 여부를 한 줄로
 * 보여주고, /rebalancing 실행 화면으로 딥링크한다. 적립 계획 탭에서 이 기능의 존재를 알리는
 * 진입점 — 실제 설정 UI는 RebalancingAlertModal의 "빠른 설정"에 있다. */
export default function AutoInvestStatusBanner() {
  const { data: portfolios } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
    staleTime: STALE_TIME.MEDIUM,
  });
  const { data: alerts } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlerts,
    queryFn: fetchRebalancingAlerts,
    staleTime: STALE_TIME.MEDIUM,
  });

  if (!portfolios || portfolios.length === 0) return null;

  const alertByPortfolioId = mergeAlertsByPortfolio(alerts ?? []);
  const activeEntry = portfolios
    .map((p) => ({ portfolio: p, alert: alertByPortfolioId[p.id] }))
    .find(({ alert }) => isDcaAutoBuyPreset(alert));

  const linkTo = activeEntry
    ? `/rebalancing?rtab=포트폴리오&portfolioId=${activeEntry.portfolio.id}`
    : `/rebalancing?rtab=포트폴리오`;

  return (
    <div className="card flex items-center gap-3">
      <div
        className={`shrink-0 p-2 rounded-full ${
          activeEntry
            ? "bg-green-100 dark:bg-green-950 text-green-600 dark:text-green-400"
            : "bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500"
        }`}
      >
        <RefreshCw size={16} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
          {activeEntry
            ? `정기 적립식 ${describeDcaAutoBuy(activeEntry.alert)}`
            : "정기 적립식 자동매수를 설정해보세요"}
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-500 truncate">
          {activeEntry
            ? activeEntry.portfolio.name
            : "매달 지정한 날짜에 목표 비중대로 자동 매수됩니다"}
        </p>
      </div>
      <Link
        to={linkTo}
        className="shrink-0 flex items-center gap-1 text-xs text-blue-500 dark:text-blue-400 hover:underline"
      >
        {activeEntry ? "설정 관리" : "설정하기"} <ArrowRight size={11} />
      </Link>
    </div>
  );
}
