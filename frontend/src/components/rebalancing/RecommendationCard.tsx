import { useEffect, useRef, useState } from "react";
import { Plus, Settings2, Target } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAgeGoalRecommendation,
  fetchHorizonGoalRecommendations,
  fetchOverallGoalRecommendation,
  type GoalRecommendationItem,
} from "@/api/rebalancing";
import { fetchSettings } from "@/api/settings";
import { fetchPortfolios, updatePortfolio, type PortfolioItem } from "@/api/portfolios";
import {
  ACCOUNT_TAX_TYPE_LABELS,
  fetchAccounts,
  INVESTMENT_HORIZON_LABELS,
  type AccountTaxType,
  type InvestmentHorizon,
} from "@/api/assets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidatePortfolioData } from "@/utils/queryInvalidation";
import { getPortfolioHorizonTaxType, getPortfolioTargetState } from "@/utils/portfolio";
import { isBankAccount, isStockAccount } from "@/utils/accounts";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { normalizeWeights } from "@/utils/recommendationDrift";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";
import { useAddSuggestedCandidates } from "@/hooks/useAddSuggestedCandidates";
import ConfirmModal from "@/components/common/ConfirmModal";
import SkeletonCard from "@/components/common/SkeletonCard";
import GoalCandidateManagerModal from "@/components/rebalancing/GoalCandidateManagerModal";
import GoalRecommendationOptionsModal from "@/components/rebalancing/GoalRecommendationOptionsModal";
import RecommendationAgeTab from "@/components/rebalancing/RecommendationAgeTab";
import RecommendationComparisonPreview from "@/components/rebalancing/RecommendationComparisonPreview";
import RecommendationHorizonTab from "@/components/rebalancing/RecommendationHorizonTab";
import RecommendationOverallTab from "@/components/rebalancing/RecommendationOverallTab";
import {
  buildApplyConfirm,
  type CreatePortfolioHandler,
  type OverallTargetSelection,
  type RecommendationTabActions,
} from "@/components/rebalancing/recommendationCardModel";

const HORIZON_ORDER: InvestmentHorizon[] = ["SHORT_TERM", "MID_TERM", "LONG_TERM"];
const TAX_TYPE_ORDER: AccountTaxType[] = [
  "GENERAL",
  "ISA",
  "PENSION_SAVINGS",
  "IRP",
  "OVERSEAS_DEDICATED",
];

type ActiveTab = "전체" | "연령대" | InvestmentHorizon;

interface Props {
  /** 추천 비중을 기준 포트폴리오에 저장한 뒤 호출된다 — 부모가 화면 전환(포트폴리오 탭 이동 등)을 담당한다. */
  onApplied?: (portfolioId: string) => void;
  /** "이 비중으로 새 포트폴리오 만들기" 클릭 시 호출 — 부모가 포트폴리오 편집 모달을 해당 비중(+ 기간별 탭이면 태그
   * 매칭 계좌)으로 미리 채워 연다. */
  onCreatePortfolio?: CreatePortfolioHandler;
  /** 마운트 시 "추천 설정" 옵션 모달을 바로 연다 — 설정탭 딥링크(openRecOptions=1)용 */
  initialOptionsOpen?: boolean;
  /** 옵션 모달이 닫힐 때 호출 — 부모가 딥링크 파라미터를 정리한다 */
  onOptionsClosed?: () => void;
}

/** 목표 역산 추천("전체")과 투자기간별 추천("단기"/"중기"/"장기")을 하나의 탭 카드로 합쳐 보여준다.
 * 둘 다 같은 후보 종목(`goal_candidate_tickers`)과 MVO 계산 엔진을 공유하지만, "전체"는 목표금액·
 * 목표연도를 역산한 필요수익률 제약을, 기간별 탭은 계좌 태그 기반 고정 리스크 성향을 사용한다는
 * 점에서 서로 다른 API 응답(`GoalRecommendation`/`HorizonGoalRecommendation`)을 소비한다.
 * "전체" 탭은 목표 미설정 상태에서도 항상 노출해 설정 유도 문구를 보여준다. */
export default function RecommendationCard({
  onApplied,
  onCreatePortfolio,
  initialOptionsOpen = false,
  onOptionsClosed,
}: Props) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<ActiveTab>("전체");

  const {
    data: overallData,
    isPending: overallPending,
    isError: overallIsError,
    refetch: refetchOverall,
  } = useQuery({
    queryKey: QUERY_KEYS.goalRecommendationOverall,
    queryFn: fetchOverallGoalRecommendation,
    staleTime: STALE_TIME.LONG,
  });

  // "기간별"/"연령대" 탭을 실제로 클릭하기 전까지는 지연 로딩 — 둘 다 MVO 최적화 + 외부
  // 가격/배당 API 호출을 수반하는 무거운 요청이라, 탭 마운트 즉시 3개를 전부 fetch하면
  // 모바일에서 체감 지연이 크다.
  const { data: horizonData, isFetching: horizonFetching } = useQuery({
    queryKey: QUERY_KEYS.goalRecommendationByHorizon,
    queryFn: fetchHorizonGoalRecommendations,
    staleTime: STALE_TIME.LONG,
    enabled: activeTab !== "전체" && activeTab !== "연령대",
  });

  const { data: ageData, isPending: agePending } = useQuery({
    queryKey: QUERY_KEYS.goalRecommendationByAge,
    queryFn: fetchAgeGoalRecommendation,
    staleTime: STALE_TIME.LONG,
    enabled: activeTab === "연령대",
  });

  const { data: portfoliosRaw } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
  });
  const portfolios = portfoliosRaw ?? [];

  const { data: accountsRaw } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
  });
  const stockAccounts = (accountsRaw ?? []).filter(
    (a) => a.is_active && isStockAccount(a.asset_type),
  );
  const bankAccounts = (accountsRaw ?? []).filter(
    (a) => a.is_active && isBankAccount(a.asset_type),
  );

  const { data: settingsData } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });
  const candidateCount = settingsData?.goal_candidate_tickers?.length ?? 0;

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
  const [selectedOverallTargetId, setSelectedOverallTargetId] = useState("");
  const effectiveOverallTargetId = selectedOverallTargetId || anchoredPortfolioIds[0] || "";
  const overallConfirmTarget =
    targetPortfolios.find((p) => p.id === effectiveOverallTargetId) ?? targetPortfolios[0];

  const [confirmOpen, setConfirmOpen] = useState(false);

  // 전체/연령대/기간별 3개 탭이 공유하는 단일 적용 뮤테이션. 기간별 탭에서 현금성 자산 반영이
  // 필요할 때만 account_ids를 함께 넘긴다(연결 계좌 자동 확장).
  const applyMutation = useMutation({
    mutationFn: async ({
      portfolioId,
      items,
      accountIds,
    }: {
      portfolioId: string;
      items: GoalRecommendationItem[];
      accountIds?: string[];
    }) => {
      const body: { items: PortfolioItem[]; account_ids?: string[] } = {
        items: normalizeWeights(items),
      };
      if (accountIds?.length) body.account_ids = accountIds;
      await updatePortfolio(portfolioId, body);
      return portfolioId;
    },
    onSuccess: async (portfolioId) => {
      setConfirmOpen(false);
      await invalidatePortfolioData(queryClient);
      onApplied?.(portfolioId);
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  const addSuggestedMutation = useAddSuggestedCandidates(
    settingsData?.goal_candidate_tickers ?? [],
  );

  const [managerOpen, setManagerOpen] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(initialOptionsOpen);

  // 최초 방문 시 백엔드가 후보를 시드하거나(seed) 세제유형 선호 지수에 맞는 큐레이션 ETF를 자동
  // 추가해 DB에 커밋할 수 있으므로, 이미 캐시된 settings 쿼리가 그 이전 값을 들고 있을 수 있다.
  // overall/horizon 중 먼저 도착하는 응답을 기준으로 1회만 재조회해 동기화한다.
  const settingsSyncedRef = useRef(false);
  useEffect(() => {
    if ((overallData || horizonData || ageData) && !settingsSyncedRef.current) {
      settingsSyncedRef.current = true;
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.settings });
    }
  }, [overallData, horizonData, ageData, queryClient]);

  if (overallPending) return <SkeletonCard rows={4} />;

  if (overallIsError || !overallData) {
    return (
      <div className="rounded-xl border border-teal-200 dark:border-teal-800/50 bg-teal-50 dark:bg-teal-900/20 p-4 flex items-center justify-between gap-2 text-sm">
        <span className="text-red-600 dark:text-red-400">추천 비중을 불러오지 못했습니다.</span>
        <button
          type="button"
          onClick={() => refetchOverall()}
          className="underline font-medium text-teal-700 dark:text-teal-400 shrink-0"
        >
          다시 시도
        </button>
      </div>
    );
  }

  const isHorizonTab = effectiveTab !== "전체" && effectiveTab !== "연령대";
  const applyConfirm = buildApplyConfirm({
    tab: isHorizonTab ? "기간별" : effectiveTab,
    overallData,
    ageData,
    overallTarget: overallConfirmTarget,
    horizonRec: activeHorizonRec,
    horizonTarget: horizonTargetPortfolio,
    cashEquivalentMatches,
  });

  const tabActions: RecommendationTabActions = {
    onAddSuggested: (candidates) => addSuggestedMutation.mutate(candidates),
    addPending: addSuggestedMutation.isPending,
    onApplyClick: () => setConfirmOpen(true),
    applyPending: applyMutation.isPending,
    onCreatePortfolio,
  };
  const overallSelection: OverallTargetSelection = {
    targetPortfolios,
    selectedTargetId: effectiveOverallTargetId,
    onSelectTarget: setSelectedOverallTargetId,
    anchoredTargetIds: anchoredPortfolioIds,
    confirmTarget: overallConfirmTarget,
  };

  return (
    <>
      <div className="rounded-xl border border-teal-200 dark:border-teal-800/50 bg-teal-50 dark:bg-teal-900/20 p-4 space-y-2">
        <div className="flex items-center gap-2">
          <Target size={13} className="text-teal-500 shrink-0" />
          <span className="text-xs font-semibold text-teal-700 dark:text-teal-400">추천 비중</span>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {(["전체", "연령대", ...availableHorizons] as ActiveTab[]).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} px-2.5 py-1 text-xs rounded-full transition-colors ${
                tab === effectiveTab
                  ? "bg-teal-600 text-white"
                  : "bg-white dark:bg-gray-800 text-teal-600 dark:text-teal-400 border border-teal-200 dark:border-teal-800/50"
              }`}
            >
              {tab === "전체" || tab === "연령대" ? tab : INVESTMENT_HORIZON_LABELS[tab]}
            </button>
          ))}
        </div>

        {effectiveTab !== "전체" && taxTypesForHorizon.length > 1 && (
          <div className="flex flex-wrap gap-1.5">
            {taxTypesForHorizon.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setSelectedTaxType(t)}
                className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} px-2 py-1 text-xs rounded-full border transition-colors ${
                  t === activeTaxType
                    ? "bg-teal-100 dark:bg-teal-800/40 border-teal-400 dark:border-teal-600 text-teal-700 dark:text-teal-300"
                    : "bg-transparent border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400"
                }`}
              >
                {ACCOUNT_TAX_TYPE_LABELS[t]}
              </button>
            ))}
          </div>
        )}

        {effectiveTab === "전체" ? (
          <RecommendationOverallTab
            data={overallData}
            selection={overallSelection}
            actions={tabActions}
          />
        ) : effectiveTab === "연령대" ? (
          <RecommendationAgeTab
            data={ageData}
            pending={agePending}
            selection={overallSelection}
            actions={tabActions}
            onOpenOptions={() => setOptionsOpen(true)}
          />
        ) : (
          <RecommendationHorizonTab
            horizon={effectiveTab}
            taxType={activeTaxType}
            rec={activeHorizonRec}
            fetching={horizonFetching}
            targetPortfolio={horizonTargetPortfolio}
            stockAccounts={stockAccounts}
            cashEquivalentMatches={cashEquivalentMatches}
            actions={tabActions}
          />
        )}

        <div className="pt-2 border-t border-teal-200 dark:border-teal-800/50 flex items-center gap-3">
          <button
            type="button"
            onClick={() => setManagerOpen(true)}
            className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-1 text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700`}
          >
            <Plus size={12} />
            후보 ETF 관리{candidateCount > 0 && ` (${candidateCount})`}
          </button>
          <button
            type="button"
            onClick={() => setOptionsOpen(true)}
            className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-1 text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700`}
          >
            <Settings2 size={12} />
            추천 설정
          </button>
        </div>
      </div>

      {managerOpen && <GoalCandidateManagerModal onClose={() => setManagerOpen(false)} />}
      {optionsOpen && (
        <GoalRecommendationOptionsModal
          onClose={() => {
            setOptionsOpen(false);
            onOptionsClosed?.();
          }}
        />
      )}

      {confirmOpen && applyConfirm && (
        <ConfirmModal
          message={applyConfirm.message}
          confirmLabel="적용"
          danger={false}
          onConfirm={() =>
            applyMutation.mutate({
              portfolioId: applyConfirm.target.id,
              items: applyConfirm.items,
              accountIds: applyConfirm.accountIds,
            })
          }
          onCancel={() => setConfirmOpen(false)}
        >
          <RecommendationComparisonPreview
            recommendedItems={applyConfirm.items}
            currentItems={applyConfirm.target.items}
            recommendedMetrics={applyConfirm.metrics}
            targetPortfolioId={applyConfirm.target.id}
          />
        </ConfirmModal>
      )}
    </>
  );
}
