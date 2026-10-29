import { useQuery } from "@tanstack/react-query";
import { rebalancingAlertsQuery } from "@/api/queryOptions";

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
    ...rebalancingAlertsQuery,
    enabled: !!portfolioId,
  });
  if (!portfolioId || !Array.isArray(data)) return { dcaAuto: false, linked: false };
  // 계좌별 알림이 여러 개일 수 있다 — mergeAlertsByPortfolio는 strategy·market_condition_mode를 첫 행 값으로
  // 남겨 다른 계좌의 적립식 자동매수를 놓치므로, 행 단위로 본다(plans/80)
  const dca = data.filter(
    (a) =>
      a.portfolio_id === portfolioId &&
      a.is_active &&
      a.mode === "AUTO" &&
      a.strategy === "BUY_ONLY",
  );
  const dcaAuto = dca.length > 0;
  // 적립식 자동매수가 모두 전술 연동일 때만 "연동됨" — 하나라도 빠지면 연동 안내를 계속 보여준다
  return { dcaAuto, linked: dcaAuto && dca.every((a) => a.market_condition_mode === "TACTICAL") };
}
