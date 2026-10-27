import { useQuery } from "@tanstack/react-query";
import { fetchAccounts } from "@/api/assets";
import { fetchTacticalStrategies } from "@/api/tactical";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { getPortfolioTargetState } from "@/utils/portfolio";
import { isStockAccount } from "@/utils/accounts";
import { portfoliosQuery } from "@/api/queryOptions";

/** URL 선택값 → 첫 우선 후보(기본은 기준 포트폴리오) → 첫 포트폴리오. 목록에 없는 URL 값(삭제됨 등)은 무시한다. */
export function resolveSelectedPortfolioId(
  requestedId: string | undefined,
  portfolioIds: string[],
  preferredIds: string[],
): string | undefined {
  if (requestedId && portfolioIds.includes(requestedId)) return requestedId;
  return preferredIds.find((id) => portfolioIds.includes(id)) ?? portfolioIds[0];
}

/**
 * 리밸런싱 페이지에서 "지금 보고 있는 포트폴리오" — 목표 조정(추천·전술)과 포트폴리오 탭이 같은 기본값을
 * 쓰게 한다(plans/64 S2). 예전엔 URL이 비면 추천=첫 기준 포트폴리오, 전술=첫 포트폴리오, 포트폴리오 탭=선택
 * 없음으로 탭마다 다른 포트폴리오가 보였다. 기본값은 URL에 쓰지 않고 파생만 한다.
 *
 * `preferTactical`이면 전술 배분을 켠 포트폴리오를 기준 포트폴리오보다 먼저 고른다 — 기준 포트폴리오는 대개
 * 전술과 무관해(국내 배당·ISA 등) 전술 모드에 들어가자마자 "꺼짐"과 종목 삭제 경고가 보였다(plans/81).
 */
export function useSelectedPortfolio(
  requestedId: string | undefined,
  { preferTactical = false }: { preferTactical?: boolean } = {},
) {
  const { data: portfoliosRaw, isLoading } = useQuery(portfoliosQuery);
  const { data: accountsRaw } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
  });
  const { data: strategiesRaw, isPending: strategiesPending } = useQuery({
    queryKey: QUERY_KEYS.tacticalStrategies,
    queryFn: fetchTacticalStrategies,
    enabled: preferTactical,
    staleTime: STALE_TIME.MEDIUM,
  });

  const portfolios = portfoliosRaw ?? [];
  const stockAccounts = (accountsRaw ?? []).filter(
    (a) => a.is_active && isStockAccount(a.asset_type),
  );
  const anchoredIds = portfolios
    .filter((p) => getPortfolioTargetState(p, stockAccounts) !== "none")
    .map((p) => p.id);
  const tacticalIds = preferTactical ? (strategiesRaw ?? []).map((s) => s.portfolio_id) : [];
  const portfolioIds = portfolios.map((p) => p.id);
  const selectedId = resolveSelectedPortfolioId(requestedId, portfolioIds, [
    ...tacticalIds,
    ...anchoredIds,
  ]);

  // URL로 고르지 않았을 때, 전술 목록이 오기 전 기준 포트폴리오로 상태를 한 번 조회했다가 바뀌지 않게 호출부가
  // 이 동안 기다린다. 조회가 실패하면 pending이 풀려 기준 포트폴리오로 진행한다
  const requestedValid = !!requestedId && portfolioIds.includes(requestedId);
  const tacticalPending = preferTactical && strategiesPending && !requestedValid;

  return { portfolios, anchoredIds, tacticalIds, selectedId, isLoading, tacticalPending };
}
