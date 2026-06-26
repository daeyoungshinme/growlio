import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, X, ArrowRight } from "lucide-react";
import { fetchDriftSummary } from "@/api/rebalancing";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

export default function RebalancingUrgentBanner() {
  const [dismissed, setDismissed] = useState(false);
  const navigate = useNavigate();

  const { data: driftData } = useQuery({
    queryKey: QUERY_KEYS.driftSummary,
    queryFn: fetchDriftSummary,
    staleTime: STALE_TIME.MEDIUM,
    refetchOnWindowFocus: false,
  });

  const urgentPortfolios = driftData?.filter((d) => d.needs_rebalancing) ?? [];

  if (!urgentPortfolios.length || dismissed) return null;

  const label =
    urgentPortfolios.length === 1
      ? `포트폴리오 "${urgentPortfolios[0].portfolio_name}"이(가) 목표 비중을 벗어났습니다.`
      : `${urgentPortfolios.length}개 포트폴리오가 목표 비중을 벗어났습니다.`;

  const firstPortfolioId = urgentPortfolios[0].portfolio_id;

  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-xl border-l-4 border-amber-500 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-500">
      <AlertTriangle size={16} className="shrink-0 text-amber-600 dark:text-amber-400" />
      <p className="flex-1 text-sm text-amber-800 dark:text-amber-300">{label}</p>
      <button
        onClick={() =>
          navigate(`/rebalancing?rtab=포트폴리오&portfolioId=${firstPortfolioId}`)
        }
        className="shrink-0 flex items-center gap-1 text-xs font-semibold text-amber-700 dark:text-amber-300 hover:underline"
      >
        리밸런싱하기 <ArrowRight size={12} />
      </button>
      <button
        onClick={() => setDismissed(true)}
        className="shrink-0 p-1 text-amber-500 hover:text-amber-700 dark:hover:text-amber-300 rounded transition-colors"
        aria-label="배너 닫기"
      >
        <X size={14} />
      </button>
    </div>
  );
}
