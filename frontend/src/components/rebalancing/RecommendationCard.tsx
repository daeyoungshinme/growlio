import { useEffect, useRef, useState } from "react";
import { Plus, Settings2, Target } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAgeGoalRecommendation,
  fetchHorizonGoalRecommendations,
  fetchOverallGoalRecommendation,
  type GoalRecommendationItem,
} from "@/api/rebalancing";
import { updatePortfolio, type PortfolioItem } from "@/api/portfolios";
import {
  ACCOUNT_TAX_TYPE_LABELS,
  fetchAccounts,
  INVESTMENT_HORIZON_LABELS,
  type AccountTaxType,
  type InvestmentHorizon,
} from "@/api/assets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidatePortfolioData, invalidateSettingsData } from "@/utils/queryInvalidation";
import { getPortfolioHorizonTaxType, getPortfolioTargetState } from "@/utils/portfolio";
import { isBankAccount, isStockAccount } from "@/utils/accounts";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { toPortfolioItemsPreservingGroups } from "@/utils/recommendationDrift";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";
import { LABEL_SM, SELECT_SM } from "@/constants/inputStyles";
import SegmentedControl from "@/components/portfolio/allocation/SegmentedControl";
import { useAddSuggestedCandidates } from "@/hooks/useAddSuggestedCandidates";
import ConfirmModal from "@/components/common/ConfirmModal";
import { useAutoExecutionNotice } from "@/hooks/useAutoExecutionNotice";

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
import { portfoliosQuery, settingsQuery } from "@/api/queryOptions";

/** 적용 확인창 안내 — 자동 실행이 켜진 포트폴리오면 다음 자동 실행이 새 목표로 주문함을 알린다(plans/63 P4-4) */
function AutoExecutionNotice({ portfolioId }: { portfolioId: string }) {
  const notice = useAutoExecutionNotice(portfolioId);
  if (!notice) return null;
  return (
    <p className="mb-2 rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-xs text-orange-700 dark:border-orange-800 dark:bg-orange-950 dark:text-orange-300">
      {notice}
    </p>
  );
}

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
  /** 페이지에서 이미 고른 포트폴리오(URL portfolioId) — 있으면 적용 대상으로 먼저 선택한다 */
  selectedPortfolioId?: string;
  /** 적용 대상 변경 시 호출 — 부모가 URL에 반영해 다른 탭과 선택을 공유한다(plans/63 P3-3) */
  onSelectPortfolio?: (portfolioId: string) => void;
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
  selectedPortfolioId,
  onSelectPortfolio,
}: Props) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<ActiveTab>("전체");

  const {
    data: overallData,
    isPending: overallPending,
    isError: overallIsError,
    isFetching: overallFetching,
    refetch: refetchOverall,
  } = useQuery({
    queryKey: QUERY_KEYS.goalRecommendationOverall,
    queryFn: fetchOverallGoalRecommendation,
    staleTime: STALE_TIME.LONG,
    // 영속 캐시(main.tsx PERSIST_QUERY_KEYS)에 남도록 — 기본 30분 gcTime이면 탭을 한동안 안 열 때
    // 저장본에서 빠져 재방문이 다시 콜드 계산(수십 초)을 기다렸다
    gcTime: STALE_TIME.DAY,
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

  const { data: portfoliosRaw } = useQuery(portfoliosQuery);
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

  const { data: settingsData } = useQuery(settingsQuery);
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
      // 대상 포트폴리오의 지수 그룹(plans/74)은 유지 — 추천이 그룹 멤버를 내면 그룹 비중으로 합산한다
      const current = portfolios.find((p) => p.id === portfolioId)?.items ?? [];
      const body: { items: PortfolioItem[]; account_ids?: string[] } = {
        items: toPortfolioItemsPreservingGroups(items, current),
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
      void invalidateSettingsData(queryClient);
    }
  }, [overallData, horizonData, ageData, queryClient]);

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
    // 추천 비중은 포트폴리오와 무관 — 대상은 적용 영역의 select에서만 고른다(목표 조정 탭에 상단 선택기 없음)
    targetPortfolios,
    selectedTargetId: effectiveOverallTargetId,
    onSelectTarget: selectOverallTarget,
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

        {/* 탭 위계: 페이지 pill → 목표 조정 underline(추천/전술) → 여기 segmented가 3단. 세제유형은
            4단 탭이 되지 않도록 select로 둔다(plans/50 위계 규칙, plans/64 S2) */}
        <SegmentedControl
          ariaLabel="추천 기준"
          stretch
          options={(["전체", "연령대", ...availableHorizons] as ActiveTab[]).map((tab) => ({
            value: tab,
            label: tab === "전체" || tab === "연령대" ? tab : INVESTMENT_HORIZON_LABELS[tab],
          }))}
          value={effectiveTab}
          onChange={setActiveTab}
        />

        {effectiveTab !== "전체" && effectiveTab !== "연령대" && taxTypesForHorizon.length > 1 && (
          <label className="flex items-center gap-2">
            <span className={LABEL_SM}>계좌 유형</span>
            <select
              className={SELECT_SM}
              value={activeTaxType}
              onChange={(e) => setSelectedTaxType(e.target.value as AccountTaxType)}
            >
              {taxTypesForHorizon.map((t) => (
                <option key={t} value={t}>
                  {ACCOUNT_TAX_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </label>
        )}

        {effectiveTab === "전체" ? (
          // 전체 추천(콜드 계산 수십 초)을 기다리는 동안에도 기준 전환·설정 버튼은 먼저 보여준다
          overallPending ? (
            <div className="space-y-2">
              <p className="text-xs text-gray-500 dark:text-gray-400">
                추천 비중을 계산하고 있어요. 처음엔 시세를 모으느라 시간이 걸릴 수 있어요.
              </p>
              <SkeletonCard rows={4} />
            </div>
          ) : overallIsError || !overallData ? (
            <div className="flex items-center justify-between gap-2 text-sm">
              <span className="text-red-600 dark:text-red-400">
                추천 비중을 불러오지 못했습니다.
              </span>
              <button
                type="button"
                onClick={() => refetchOverall()}
                className="underline font-medium text-teal-700 dark:text-teal-400 shrink-0"
              >
                다시 시도
              </button>
            </div>
          ) : (
            <>
              {overallFetching && (
                <p className="text-xs text-gray-400 dark:text-gray-500">
                  최신 추천으로 업데이트 중…
                </p>
              )}
              <RecommendationOverallTab
                data={overallData}
                selection={overallSelection}
                actions={tabActions}
              />
            </>
          )
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
          <AutoExecutionNotice portfolioId={applyConfirm.target.id} />
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
