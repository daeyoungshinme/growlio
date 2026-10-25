import { useQuery } from "@tanstack/react-query";
import { fetchRebalancingAlerts } from "@/api/alerts";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { mergeAlertsByPortfolio } from "@/utils/portfolio";

export interface DcaTacticalLink {
  /** 활성 AUTO + BUY_ONLY(매수만) 자동매수 — 적립식 코어로 운용 중 */
  dcaAuto: boolean;
  /** 그 자동매수가 전술 연동(`market_condition_mode="TACTICAL"`) — 방어 국면이면 매수 보류 */
  linked: boolean;
}

/**
 * 전술 탭이 "적립식 코어 + 전술 보조" 안내를 고르는 데 쓴다(plans/71). 적립식엔 제안 비중 적용(매도)보다
 * 자동매수 전술 연동(매수 보류)이 낫다는 백테스트 결론을 해당 포트폴리오에만 보여준다.
 */
export function useDcaTacticalLink(portfolioId: string | undefined): DcaTacticalLink {
  const { data } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlerts,
    queryFn: fetchRebalancingAlerts,
    staleTime: STALE_TIME.MEDIUM,
    enabled: !!portfolioId,
  });
  if (!portfolioId || !Array.isArray(data)) return { dcaAuto: false, linked: false };
  const alert = mergeAlertsByPortfolio(data)[portfolioId];
  const dcaAuto = !!alert?.is_active && alert.mode === "AUTO" && alert.strategy === "BUY_ONLY";
  return { dcaAuto, linked: dcaAuto && alert?.market_condition_mode === "TACTICAL" };
}
