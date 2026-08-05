import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Plus, Settings2, Target } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAgeGoalRecommendation,
  fetchHorizonGoalRecommendations,
  fetchOverallGoalRecommendation,
  fetchPortfolioExpectedMetrics,
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
import { fmtKrw } from "@/utils/format";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";
import { useAddSuggestedCandidates } from "@/hooks/useAddSuggestedCandidates";
import ConfirmModal from "@/components/common/ConfirmModal";
import SkeletonCard from "@/components/common/SkeletonCard";
import GoalCandidateManagerModal from "@/components/rebalancing/GoalCandidateManagerModal";
import GoalRecommendationOptionsModal from "@/components/rebalancing/GoalRecommendationOptionsModal";
import RecommendationResultPanel from "@/components/rebalancing/RecommendationResultPanel";
import PortfolioWeightChart from "@/components/portfolio-analysis/PortfolioWeightChart";
import {
  buildWeightDiffRows,
  computeRecommendationDrift,
  hasSignificantDrift,
} from "@/utils/recommendationDrift";

const HORIZON_ORDER: InvestmentHorizon[] = ["SHORT_TERM", "MID_TERM", "LONG_TERM"];
const TAX_TYPE_ORDER: AccountTaxType[] = [
  "GENERAL",
  "ISA",
  "PENSION_SAVINGS",
  "IRP",
  "OVERSEAS_DEDICATED",
];

const RISK_TOLERANCE_LABELS: Record<string, string> = {
  CONSERVATIVE: "보수적",
  BALANCED: "중립",
  AGGRESSIVE: "공격적",
};

type ActiveTab = "전체" | "연령대" | InvestmentHorizon;

function normalizeWeights(items: GoalRecommendationItem[]): PortfolioItem[] {
  const normalized = items.map((i) => ({
    ticker: i.ticker,
    name: i.name,
    market: i.market,
    weight: Math.round(i.weight * 10) / 10,
  }));
  const diff = Math.round((100 - normalized.reduce((s, i) => s + i.weight, 0)) * 10) / 10;
  if (normalized.length > 0 && diff !== 0) normalized[normalized.length - 1].weight += diff;
  return normalized;
}

function MetricCompareCell({
  label,
  current,
  recommended,
  loading,
}: {
  label: string;
  current: number | null | undefined;
  recommended: number | null;
  loading: boolean;
}) {
  return (
    <div>
      <p className="text-gray-400 dark:text-gray-500">{label}</p>
      <p className="text-gray-700 dark:text-gray-300">
        <span>{loading ? "…" : current != null ? `${current.toFixed(1)}%` : "—"}</span>
        {" → "}
        <span className="text-teal-600 dark:text-teal-400 font-medium">
          {recommended != null ? `${recommended.toFixed(1)}%` : "—"}
        </span>
      </p>
    </div>
  );
}

/** "적용" 확인창에 표시되는 비교 미리보기 — 종목별 현재 vs 추천 비중 테이블 + 기대수익률/변동성/
 * 배당수익률 요약. 현재 포트폴리오 쪽 지표는 확인창이 열릴 때만 온디맨드로 조회한다(캐싱 없음). */
function RecommendationComparisonPreview({
  recommendedItems,
  currentItems,
  recommendedMetrics,
  targetPortfolioId,
}: {
  recommendedItems: GoalRecommendationItem[];
  currentItems: PortfolioItem[];
  recommendedMetrics: {
    expected_return_pct: number | null;
    expected_dividend_yield_pct: number | null;
    expected_volatility_pct: number | null;
  };
  targetPortfolioId: string;
}) {
  const { data: currentMetrics, isLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolioExpectedMetrics(targetPortfolioId),
    queryFn: () => fetchPortfolioExpectedMetrics(targetPortfolioId),
  });

  const rows = buildWeightDiffRows(recommendedItems, currentItems);

  return (
    <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <p className="text-center text-xs text-gray-400 dark:text-gray-500">현재</p>
          <PortfolioWeightChart items={currentItems} />
        </div>
        <div>
          <p className="text-center text-xs text-teal-600 dark:text-teal-400 font-medium">추천</p>
          <PortfolioWeightChart items={recommendedItems} />
        </div>
      </div>
      <div className="max-h-40 overflow-y-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-400 dark:text-gray-500">
              <th className="text-left font-normal pb-1">종목</th>
              <th className="text-right font-normal pb-1">현재</th>
              <th className="text-right font-normal pb-1">추천</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="text-gray-700 dark:text-gray-300">
                <td className="py-0.5 pr-2 truncate max-w-[140px]">{row.name}</td>
                <td className="text-right py-0.5 text-gray-400 dark:text-gray-500">
                  {row.currentWeight != null ? `${row.currentWeight.toFixed(1)}%` : "—"}
                </td>
                <td className="text-right py-0.5 font-medium text-teal-600 dark:text-teal-400">
                  {row.recommendedWeight != null ? `${row.recommendedWeight.toFixed(1)}%` : "0%"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pt-2 border-t border-gray-100 dark:border-gray-800 grid grid-cols-3 gap-2 text-xs">
        <MetricCompareCell
          label="기대수익률"
          current={currentMetrics?.expected_return_pct}
          recommended={recommendedMetrics.expected_return_pct}
          loading={isLoading}
        />
        <MetricCompareCell
          label="변동성"
          current={currentMetrics?.expected_volatility_pct}
          recommended={recommendedMetrics.expected_volatility_pct}
          loading={isLoading}
        />
        <MetricCompareCell
          label="배당수익률"
          current={currentMetrics?.expected_dividend_yield_pct}
          recommended={recommendedMetrics.expected_dividend_yield_pct}
          loading={isLoading}
        />
      </div>
    </div>
  );
}

interface Props {
  /** 추천 비중을 기준 포트폴리오에 저장한 뒤 호출된다 — 부모가 화면 전환(포트폴리오 탭 이동 등)을 담당한다. */
  onApplied?: (portfolioId: string) => void;
  /** "이 비중으로 새 포트폴리오 만들기" 클릭 시 호출 — 부모가 포트폴리오 편집 모달을 해당 비중(+ 기간별 탭이면 태그
   * 매칭 계좌)으로 미리 채워 연다. */
  onCreatePortfolio?: (
    items: PortfolioItem[],
    suggestedName: string,
    accountIds?: string[],
  ) => void;
}

/** 목표 역산 추천("전체")과 투자기간별 추천("단기"/"중기"/"장기")을 하나의 탭 카드로 합쳐 보여준다.
 * 둘 다 같은 후보 종목(`goal_candidate_tickers`)과 MVO 계산 엔진을 공유하지만, "전체"는 목표금액·
 * 목표연도를 역산한 필요수익률 제약을, 기간별 탭은 계좌 태그 기반 고정 리스크 성향을 사용한다는
 * 점에서 서로 다른 API 응답(`GoalRecommendation`/`HorizonGoalRecommendation`)을 소비한다.
 * "전체" 탭은 목표 미설정 상태에서도 항상 노출해 설정 유도 문구를 보여준다. */
export default function RecommendationCard({ onApplied, onCreatePortfolio }: Props) {
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

  const targetPortfolios = portfolios.filter(
    (p) => getPortfolioTargetState(p, stockAccounts) !== "none",
  );
  const [selectedOverallTargetId, setSelectedOverallTargetId] = useState("");
  const overallConfirmTarget =
    targetPortfolios.find((p) => p.id === selectedOverallTargetId) ?? targetPortfolios[0];

  const [confirmOpen, setConfirmOpen] = useState(false);

  const applyOverallMutation = useMutation({
    mutationFn: async (portfolioId: string) => {
      if (!overallData) throw new Error("추천 비중이 없습니다");
      await updatePortfolio(portfolioId, {
        items: normalizeWeights(overallData.recommended_items),
      });
      return portfolioId;
    },
    onSuccess: async (portfolioId) => {
      setConfirmOpen(false);
      await invalidatePortfolioData(queryClient);
      onApplied?.(portfolioId);
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  const applyAgeMutation = useMutation({
    mutationFn: async (portfolioId: string) => {
      if (!ageData) throw new Error("추천 비중이 없습니다");
      await updatePortfolio(portfolioId, {
        items: normalizeWeights(ageData.recommended_items),
      });
      return portfolioId;
    },
    onSuccess: async (portfolioId) => {
      setConfirmOpen(false);
      await invalidatePortfolioData(queryClient);
      onApplied?.(portfolioId);
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  const applyHorizonMutation = useMutation({
    mutationFn: async () => {
      if (!activeHorizonRec || !horizonTargetPortfolio) throw new Error("추천 비중이 없습니다");
      const body: { items: PortfolioItem[]; account_ids?: string[] } = {
        items: normalizeWeights(activeHorizonRec.recommended_items),
      };
      if (activeHorizonRec.includes_cash_equivalent && horizonTargetPortfolio.account_ids?.length) {
        body.account_ids = Array.from(
          new Set([
            ...horizonTargetPortfolio.account_ids,
            ...cashEquivalentMatches.map((a) => a.id),
          ]),
        );
      }
      await updatePortfolio(horizonTargetPortfolio.id, body);
      return horizonTargetPortfolio.id;
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
  const [optionsOpen, setOptionsOpen] = useState(false);

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

  const hasOverallRecommendation =
    overallData.is_configured && overallData.recommended_items.length > 0;

  const overallDrift =
    hasOverallRecommendation && overallConfirmTarget
      ? computeRecommendationDrift(overallData.recommended_items, overallConfirmTarget.items)
      : null;
  const horizonDrift =
    activeHorizonRec && activeHorizonRec.recommended_items.length > 0 && horizonTargetPortfolio
      ? computeRecommendationDrift(activeHorizonRec.recommended_items, horizonTargetPortfolio.items)
      : null;
  const hasAgeRecommendation =
    !!ageData && ageData.is_configured && ageData.recommended_items.length > 0;
  const ageDrift =
    hasAgeRecommendation && ageData && overallConfirmTarget
      ? computeRecommendationDrift(ageData.recommended_items, overallConfirmTarget.items)
      : null;

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
          !overallData.is_configured ? (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {overallData.note ?? "목표금액·목표연도를 설정하면 추천을 받을 수 있습니다"}
              </p>
              <Link
                to="/invest-plan"
                className="flex items-center gap-1 text-xs font-semibold text-teal-600 dark:text-teal-400 hover:underline shrink-0"
              >
                목표 설정하러 가기 <ArrowRight size={12} />
              </Link>
            </div>
          ) : (
            <>
              {hasOverallRecommendation ? (
                <>
                  <p className="text-xs text-gray-600 dark:text-gray-300">
                    목표 달성에 필요한 연 수익률 {overallData.required_return_pct?.toFixed(1)}%
                    {overallData.required_dividend_yield_pct != null &&
                      ` · 목표 배당수익률 연 ${overallData.required_dividend_yield_pct.toFixed(1)}%`}{" "}
                    — 아래 비중으로 조정하면 기대수익률{" "}
                    {overallData.expected_return_pct?.toFixed(1)}% (최근{" "}
                    {overallData.cagr_lookback_years}년 CAGR 기준)
                    {overallData.expected_dividend_yield_pct != null &&
                      ` (배당수익률 약 ${overallData.expected_dividend_yield_pct.toFixed(1)}%)`}
                    를 기대할 수 있습니다.
                    {overallData.expected_volatility_pct != null &&
                      ` 예상 변동성은 연 ${overallData.expected_volatility_pct.toFixed(1)}%입니다.`}
                  </p>

                  <RecommendationResultPanel
                    drift={overallDrift && hasSignificantDrift(overallDrift) ? overallDrift : null}
                    items={overallData.recommended_items}
                    note={overallData.note}
                    marketSignalLevel={overallData.market_signal_level}
                    suggestedCandidates={overallData.suggested_candidates}
                    onAddSuggested={() =>
                      addSuggestedMutation.mutate(overallData.suggested_candidates)
                    }
                    addPending={addSuggestedMutation.isPending}
                    applySection={{
                      targetPortfolios,
                      selectedTargetId: selectedOverallTargetId,
                      onSelectTarget: setSelectedOverallTargetId,
                      onApplyClick: () => setConfirmOpen(true),
                      applyPending: applyOverallMutation.isPending,
                      noTargetMessage:
                        "포트폴리오 탭에서 기준 포트폴리오를 지정하면 추천 비중을 바로 적용할 수 있어요.",
                      onCreatePortfolio: onCreatePortfolio
                        ? () =>
                            onCreatePortfolio(
                              normalizeWeights(overallData.recommended_items),
                              "추천 포트폴리오",
                            )
                        : undefined,
                    }}
                  />
                </>
              ) : (
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {overallData.note ?? "추천을 계산할 수 없습니다 — 후보 ETF를 등록해주세요"}
                </p>
              )}
            </>
          )
        ) : effectiveTab === "연령대" ? (
          !ageData ? (
            agePending ? (
              <SkeletonCard rows={2} />
            ) : null
          ) : !ageData.is_configured ? (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {ageData.note ?? "연령대를 설정하면 연령대별 추천을 받을 수 있습니다"}
              </p>
              <button
                type="button"
                onClick={() => setOptionsOpen(true)}
                className="flex items-center gap-1 text-xs font-semibold text-teal-600 dark:text-teal-400 hover:underline shrink-0"
              >
                연령대 설정하기 <ArrowRight size={12} />
              </button>
            </div>
          ) : (
            <>
              {hasAgeRecommendation ? (
                <>
                  <p className="text-xs text-gray-600 dark:text-gray-300">
                    {ageData.age_bracket} 기준 리스크 성향{" "}
                    {RISK_TOLERANCE_LABELS[ageData.risk_tolerance] ?? ageData.risk_tolerance}
                    {ageData.required_dividend_yield_pct != null &&
                      ` · 목표 배당수익률 연 ${ageData.required_dividend_yield_pct.toFixed(1)}%`}
                    {ageData.expected_return_pct != null &&
                      ` · 기대수익률 ${ageData.expected_return_pct.toFixed(1)}%`}
                    {ageData.expected_dividend_yield_pct != null &&
                      ` · 배당수익률 약 ${ageData.expected_dividend_yield_pct.toFixed(1)}%`}
                    {ageData.expected_volatility_pct != null &&
                      ` · 예상 변동성 연 ${ageData.expected_volatility_pct.toFixed(1)}%`}
                  </p>

                  <RecommendationResultPanel
                    drift={ageDrift && hasSignificantDrift(ageDrift) ? ageDrift : null}
                    items={ageData.recommended_items}
                    note={ageData.note}
                    marketSignalLevel={ageData.market_signal_level}
                    extraNoticeAfterWeightList={
                      ageData.includes_cash_equivalent ? (
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          현금성 자산(CMA·파킹통장 등) 합성 비중이 포함되어 있어요 — 실제 계좌와
                          연결해 목표 비중에 반영해주세요.
                        </p>
                      ) : undefined
                    }
                    suggestedCandidates={ageData.suggested_candidates}
                    onAddSuggested={() => addSuggestedMutation.mutate(ageData.suggested_candidates)}
                    addPending={addSuggestedMutation.isPending}
                    applySection={{
                      targetPortfolios,
                      selectedTargetId: selectedOverallTargetId,
                      onSelectTarget: setSelectedOverallTargetId,
                      onApplyClick: () => setConfirmOpen(true),
                      applyPending: applyAgeMutation.isPending,
                      noTargetMessage:
                        "포트폴리오 탭에서 기준 포트폴리오를 지정하면 추천 비중을 바로 적용할 수 있어요.",
                      onCreatePortfolio: onCreatePortfolio
                        ? () =>
                            onCreatePortfolio(
                              normalizeWeights(ageData.recommended_items),
                              "연령대별 추천 포트폴리오",
                            )
                        : undefined,
                    }}
                  />
                </>
              ) : (
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {ageData.note ?? "추천을 계산할 수 없습니다 — 후보 ETF를 등록해주세요"}
                </p>
              )}
            </>
          )
        ) : activeHorizonRec ? (
          <>
            <p className="text-xs text-gray-600 dark:text-gray-300">
              {INVESTMENT_HORIZON_LABELS[effectiveTab]} · {ACCOUNT_TAX_TYPE_LABELS[activeTaxType]}{" "}
              태그 계좌 {activeHorizonRec.account_count}개 · 자산총액{" "}
              {fmtKrw(activeHorizonRec.base_krw)} · 리스크 성향{" "}
              {RISK_TOLERANCE_LABELS[activeHorizonRec.risk_tolerance] ??
                activeHorizonRec.risk_tolerance}
              {activeHorizonRec.required_dividend_yield_pct != null &&
                ` · 목표 배당수익률 연 ${activeHorizonRec.required_dividend_yield_pct.toFixed(1)}%`}
              {activeHorizonRec.recommended_items.length > 0 &&
                activeHorizonRec.expected_return_pct != null &&
                ` · 기대수익률 ${activeHorizonRec.expected_return_pct.toFixed(1)}%`}
              {activeHorizonRec.recommended_items.length > 0 &&
                activeHorizonRec.expected_dividend_yield_pct != null &&
                ` · 배당수익률 약 ${activeHorizonRec.expected_dividend_yield_pct.toFixed(1)}%`}
              {activeHorizonRec.recommended_items.length > 0 &&
                activeHorizonRec.expected_volatility_pct != null &&
                ` · 예상 변동성 연 ${activeHorizonRec.expected_volatility_pct.toFixed(1)}%`}
            </p>

            {activeHorizonRec.recommended_items.length > 0 ? (
              <RecommendationResultPanel
                drift={horizonDrift && hasSignificantDrift(horizonDrift) ? horizonDrift : null}
                items={activeHorizonRec.recommended_items}
                note={activeHorizonRec.note}
                marketSignalLevel={activeHorizonRec.market_signal_level}
                suggestedCandidates={activeHorizonRec.suggested_candidates}
                onAddSuggested={() =>
                  addSuggestedMutation.mutate(activeHorizonRec.suggested_candidates)
                }
                addPending={addSuggestedMutation.isPending}
                extraNoticeBeforeApply={
                  activeHorizonRec.includes_cash_equivalent &&
                  cashEquivalentMatches.length === 0 ? (
                    <p className="text-xs text-gray-500 dark:text-gray-400 pt-2 border-t border-teal-200 dark:border-teal-800/50">
                      현금성 자산(CMA·파킹통장 등)이 포함된 추천이에요 — 계좌 관리에서 CMA/파킹통장
                      계좌에 "{INVESTMENT_HORIZON_LABELS[effectiveTab]}" 기간 태그를 지정하면 자동
                      적용할 수 있어요.
                    </p>
                  ) : undefined
                }
                applySection={
                  activeHorizonRec.includes_cash_equivalent && cashEquivalentMatches.length === 0
                    ? null
                    : {
                        targetPortfolios: horizonTargetPortfolio ? [horizonTargetPortfolio] : [],
                        selectedTargetId: horizonTargetPortfolio?.id ?? "",
                        onSelectTarget: () => {},
                        onApplyClick: () => setConfirmOpen(true),
                        applyPending: applyHorizonMutation.isPending,
                        noTargetMessage:
                          "포트폴리오 탭에서 이 기간·계좌유형에 해당하는 계좌를 태그하고 기준 포트폴리오로 지정하면 추천 비중을 바로 적용할 수 있어요.",
                        extraCopyBeforeButtons: activeHorizonRec.includes_cash_equivalent ? (
                          <p className="text-xs text-teal-600 dark:text-teal-500">
                            현금성 자산 반영을 위해{" "}
                            {cashEquivalentMatches.map((a) => a.name).join(", ")} 계좌가
                            포트폴리오에 자동으로 연결됩니다.
                          </p>
                        ) : undefined,
                        onCreatePortfolio: onCreatePortfolio
                          ? () =>
                              onCreatePortfolio(
                                normalizeWeights(activeHorizonRec.recommended_items),
                                `${INVESTMENT_HORIZON_LABELS[effectiveTab]} 추천 포트폴리오`,
                                [
                                  ...stockAccounts
                                    .filter(
                                      (a) =>
                                        a.investment_horizon === effectiveTab &&
                                        a.tax_type === activeTaxType,
                                    )
                                    .map((a) => a.id),
                                  ...cashEquivalentMatches.map((a) => a.id),
                                ],
                              )
                          : undefined,
                      }
                }
              />
            ) : (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {activeHorizonRec.note ?? "추천을 계산할 수 없습니다"}
              </p>
            )}
          </>
        ) : horizonFetching ? (
          <SkeletonCard rows={2} />
        ) : null}

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
      {optionsOpen && <GoalRecommendationOptionsModal onClose={() => setOptionsOpen(false)} />}

      {confirmOpen && effectiveTab === "전체" && overallConfirmTarget && (
        <ConfirmModal
          message={`${overallConfirmTarget.name}의 목표 비중이 추천 비중으로 즉시 업데이트되고, 리밸런싱 분석이 자동으로 실행됩니다. 계속하시겠습니까?`}
          confirmLabel="적용"
          danger={false}
          onConfirm={() => applyOverallMutation.mutate(overallConfirmTarget.id)}
          onCancel={() => setConfirmOpen(false)}
        >
          <RecommendationComparisonPreview
            recommendedItems={overallData.recommended_items}
            currentItems={overallConfirmTarget.items}
            recommendedMetrics={{
              expected_return_pct: overallData.expected_return_pct,
              expected_dividend_yield_pct: overallData.expected_dividend_yield_pct,
              expected_volatility_pct: overallData.expected_volatility_pct,
            }}
            targetPortfolioId={overallConfirmTarget.id}
          />
        </ConfirmModal>
      )}

      {confirmOpen && effectiveTab === "연령대" && ageData && overallConfirmTarget && (
        <ConfirmModal
          message={`${overallConfirmTarget.name}의 목표 비중이 추천 비중으로 즉시 업데이트되고, 리밸런싱 분석이 자동으로 실행됩니다. 계속하시겠습니까?`}
          confirmLabel="적용"
          danger={false}
          onConfirm={() => applyAgeMutation.mutate(overallConfirmTarget.id)}
          onCancel={() => setConfirmOpen(false)}
        >
          <RecommendationComparisonPreview
            recommendedItems={ageData.recommended_items}
            currentItems={overallConfirmTarget.items}
            recommendedMetrics={{
              expected_return_pct: ageData.expected_return_pct,
              expected_dividend_yield_pct: ageData.expected_dividend_yield_pct,
              expected_volatility_pct: ageData.expected_volatility_pct,
            }}
            targetPortfolioId={overallConfirmTarget.id}
          />
        </ConfirmModal>
      )}

      {confirmOpen &&
        effectiveTab !== "전체" &&
        effectiveTab !== "연령대" &&
        horizonTargetPortfolio && (
          <ConfirmModal
            message={
              activeHorizonRec?.includes_cash_equivalent && cashEquivalentMatches.length > 0
                ? `${horizonTargetPortfolio.name}의 목표 비중이 추천 비중으로 즉시 업데이트되고, 현금성 자산 반영을 위해 ${cashEquivalentMatches.map((a) => a.name).join(", ")} 계좌가 포트폴리오에 자동으로 연결됩니다. 리밸런싱 분석이 자동으로 실행됩니다. 계속하시겠습니까?`
                : `${horizonTargetPortfolio.name}의 목표 비중이 추천 비중으로 즉시 업데이트되고, 리밸런싱 분석이 자동으로 실행됩니다. 계속하시겠습니까?`
            }
            confirmLabel="적용"
            danger={false}
            onConfirm={() => applyHorizonMutation.mutate()}
            onCancel={() => setConfirmOpen(false)}
          >
            {activeHorizonRec && (
              <RecommendationComparisonPreview
                recommendedItems={activeHorizonRec.recommended_items}
                currentItems={horizonTargetPortfolio.items}
                recommendedMetrics={{
                  expected_return_pct: activeHorizonRec.expected_return_pct,
                  expected_dividend_yield_pct: activeHorizonRec.expected_dividend_yield_pct,
                  expected_volatility_pct: activeHorizonRec.expected_volatility_pct,
                }}
                targetPortfolioId={horizonTargetPortfolio.id}
              />
            )}
          </ConfirmModal>
        )}
    </>
  );
}
