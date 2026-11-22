/** 목표 조정 › 추천 카드의 적용 대상 파생 — 어떤 탭(기간·세제유형)을 보여 줄지, 어느 포트폴리오에 적용할지.
 * 화면 렌더와 무관한 계산이라 `RecommendationCard`에서 분리했다(plans/145 PR2). */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { HorizonRecommendationResponse } from "@/api/rebalancing";
import type { AccountTaxType, InvestmentHorizon } from "@/api/assets";
import { accountsQuery, portfoliosQuery } from "@/api/queryOptions";
import { getPortfolioHorizonTaxType, getPortfolioTargetState } from "@/utils/portfolio";
import { isBankAccount, isStockAccount } from "@/utils/accounts";

export type ActiveTab = "전체" | "연령대" | InvestmentHorizon;

const HORIZON_ORDER: InvestmentHorizon[] = ["SHORT_TERM", "MID_TERM", "LONG_TERM"];
const TAX_TYPE_ORDER: AccountTaxType[] = [
  "GENERAL",
  "ISA",
  "PENSION_SAVINGS",
  "IRP",
  "OVERSEAS_DEDICATED",
];

export function useRecommendationTargets({
  activeTab,
  horizonData,
  selectedPortfolioId,
  onSelectPortfolio,
}: {
  activeTab: ActiveTab;
  horizonData: HorizonRecommendationResponse | undefined;
  selectedPortfolioId?: string;
  onSelectPortfolio?: (portfolioId: string) => void;
}) {
  const { data: portfoliosRaw } = useQuery(portfoliosQuery);
  const portfolios = portfoliosRaw ?? [];

  const { data: accountsRaw } = useQuery(accountsQuery);
  const stockAccounts = (accountsRaw ?? []).filter(
    (a) => a.is_active && isStockAccount(a.asset_type),
  );
  const bankAccounts = (accountsRaw ?? []).filter(
    (a) => a.is_active && isBankAccount(a.asset_type),
  );

  const horizonRecommendations = horizonData?.recommendations ?? [];

  // 어떤 (기간, 세제유형) 탭 버튼을 보여줄지는 horizonData(지연 로딩됨) 대신 이미 즉시 fetch되는
  // accountsRaw에서 파생한다 — 백엔드 goal_recommendation_service.py의 콤보 판별 조건
  // (is_active == True and investment_horizon is not None)과 반드시 동일하게 유지할 것.
  const taggedAccounts = (accountsRaw ?? []).filter((a) => a.is_active && a.investment_horizon);
  const availableHorizons = HORIZON_ORDER.filter((h) =>
    taggedAccounts.some((a) => a.investment_horizon === h),
  );

  const effectiveTab: ActiveTab =
    activeTab === "전체" || activeTab === "연령대" || availableHorizons.includes(activeTab)
      ? activeTab
      : "전체";

  const taxTypesForHorizon = TAX_TYPE_ORDER.filter((t) =>
    taggedAccounts.some(
      (a) => a.investment_horizon === effectiveTab && (a.tax_type ?? "GENERAL") === t,
    ),
  );
  const [selectedTaxType, setSelectedTaxType] = useState<AccountTaxType | null>(null);
  const activeTaxType =
    selectedTaxType && taxTypesForHorizon.includes(selectedTaxType)
      ? selectedTaxType
      : taxTypesForHorizon[0];

  const activeHorizonRec =
    effectiveTab !== "전체"
      ? horizonRecommendations.find(
          (r) => r.investment_horizon === effectiveTab && r.tax_type === activeTaxType,
        )
      : undefined;

  // 현금성 자산(CASH_EQUIVALENT) 추천 항목의 실제 근거가 되는, 같은 기간·세제유형 태그를 가진
  // CMA/파킹통장 계좌 — 적용/생성 시 account_ids에 자동으로 함께 연결해 목표비중이 실제로
  // 계산되도록 한다(연결 안 하면 목표비중은 잡히는데 현재값이 영구히 0으로 남음).
  const cashEquivalentMatches =
    effectiveTab !== "전체" && activeTaxType
      ? bankAccounts.filter(
          (a) => a.investment_horizon === effectiveTab && a.tax_type === activeTaxType,
        )
      : [];

  const horizonTargetPortfolio =
    effectiveTab !== "전체" && activeTaxType
      ? portfolios.find((p) => {
          const match = getPortfolioHorizonTaxType(p, stockAccounts);
          return match?.horizon === effectiveTab && match?.taxType === activeTaxType;
        })
      : undefined;

  // 전체/연령대 추천은 어느 포트폴리오에나 적용할 수 있다 — 예전엔 "기준 포트폴리오"로 지정된 것만
  // 후보로 잡아 미지정 사용자는 안내문만 보고 적용 버튼을 못 찾았음(U7). 기준 포트폴리오를 앞에 두고 기본 선택.
  const anchoredPortfolioIds = portfolios
    .filter((p) => getPortfolioTargetState(p, stockAccounts) !== "none")
    .map((p) => p.id);
  const targetPortfolios = [...portfolios].sort(
    (a, b) =>
      Number(anchoredPortfolioIds.includes(b.id)) - Number(anchoredPortfolioIds.includes(a.id)),
  );
  // 부모가 URL로 관리하면(onSelectPortfolio) URL이 단일 진실, 아니면 카드 내부 상태
  const [localTargetId, setLocalTargetId] = useState("");
  const requestedTargetId = onSelectPortfolio ? (selectedPortfolioId ?? "") : localTargetId;
  const effectiveOverallTargetId =
    (portfolios.some((p) => p.id === requestedTargetId) ? requestedTargetId : "") ||
    anchoredPortfolioIds[0] ||
    "";
  const selectOverallTarget = (id: string) =>
    onSelectPortfolio ? onSelectPortfolio(id) : setLocalTargetId(id);
  const overallConfirmTarget =
    targetPortfolios.find((p) => p.id === effectiveOverallTargetId) ?? targetPortfolios[0];

  return {
    portfolios,
    stockAccounts,
    availableHorizons,
    effectiveTab,
    taxTypesForHorizon,
    activeTaxType,
    setSelectedTaxType,
    activeHorizonRec,
    cashEquivalentMatches,
    horizonTargetPortfolio,
    anchoredPortfolioIds,
    targetPortfolios,
    effectiveOverallTargetId,
    selectOverallTarget,
    overallConfirmTarget,
  };
}
