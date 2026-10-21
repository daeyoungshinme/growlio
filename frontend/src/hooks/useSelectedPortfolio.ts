import { useQuery } from "@tanstack/react-query";
import { fetchPortfolios } from "@/api/portfolios";
import { fetchAccounts } from "@/api/assets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { getPortfolioTargetState } from "@/utils/portfolio";
import { isStockAccount } from "@/utils/accounts";

/** URL 선택값 → 첫 기준 포트폴리오 → 첫 포트폴리오. 목록에 없는 URL 값(삭제됨 등)은 무시한다. */
export function resolveSelectedPortfolioId(
  requestedId: string | undefined,
  portfolioIds: string[],
  anchoredIds: string[],
): string | undefined {
  if (requestedId && portfolioIds.includes(requestedId)) return requestedId;
  return anchoredIds[0] ?? portfolioIds[0];
}

/**
 * 리밸런싱 페이지에서 "지금 보고 있는 포트폴리오" — 목표 조정(추천·전술)과 포트폴리오 탭이 같은 기본값을
 * 쓰게 한다(plans/64 S2). 예전엔 URL이 비면 추천=첫 기준 포트폴리오, 전술=첫 포트폴리오, 포트폴리오 탭=선택
 * 없음으로 탭마다 다른 포트폴리오가 보였다. 기본값은 URL에 쓰지 않고 파생만 한다.
 */
export function useSelectedPortfolio(requestedId: string | undefined) {
  const { data: portfoliosRaw, isLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
    staleTime: STALE_TIME.MEDIUM,
  });
  const { data: accountsRaw } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
  });

  const portfolios = portfoliosRaw ?? [];
  const stockAccounts = (accountsRaw ?? []).filter(
    (a) => a.is_active && isStockAccount(a.asset_type),
  );
  const anchoredIds = portfolios
    .filter((p) => getPortfolioTargetState(p, stockAccounts) !== "none")
    .map((p) => p.id);
  const selectedId = resolveSelectedPortfolioId(
    requestedId,
    portfolios.map((p) => p.id),
    anchoredIds,
  );

  return { portfolios, anchoredIds, selectedId, isLoading };
}
