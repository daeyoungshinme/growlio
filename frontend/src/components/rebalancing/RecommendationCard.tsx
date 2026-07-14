import { useEffect, useRef, useState } from "react";
import { Loader2, Plus, Settings2, Target } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CASH_EQUIVALENT_TICKER,
  fetchHorizonGoalRecommendations,
  fetchOverallGoalRecommendation,
  type GoalRecommendationItem,
} from "@/api/rebalancing";
import { fetchSettings } from "@/api/settings";
import { fetchPortfolios, updatePortfolio } from "@/api/portfolios";
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
import { isStockAccount } from "@/utils/accounts";
import { fmtKrw } from "@/utils/format";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import ConfirmModal from "@/components/common/ConfirmModal";
import GoalCandidateManagerModal from "@/components/rebalancing/GoalCandidateManagerModal";
import GoalRecommendationOptionsModal from "@/components/rebalancing/GoalRecommendationOptionsModal";

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

type ActiveTab = "전체" | InvestmentHorizon;

function normalizeWeights(items: GoalRecommendationItem[]) {
  const normalized = items.map((i) => ({ ...i, weight: Math.round(i.weight * 10) / 10 }));
  const diff = Math.round((100 - normalized.reduce((s, i) => s + i.weight, 0)) * 10) / 10;
  if (normalized.length > 0 && diff !== 0) normalized[normalized.length - 1].weight += diff;
  return normalized;
}

interface Props {
  /** 추천 비중을 목표 포트폴리오에 저장한 뒤 호출된다 — 부모가 화면 전환(포트폴리오 탭 이동 등)을 담당한다. */
  onApplied?: (portfolioId: string) => void;
}

/** 목표 역산 추천("전체")과 투자기간별 추천("단기"/"중기"/"장기")을 하나의 탭 카드로 합쳐 보여준다.
 * 둘 다 같은 후보 종목(`goal_candidate_tickers`)과 MVO 계산 엔진을 공유하지만, "전체"는 목표금액·
 * 목표연도를 역산한 필요수익률 제약을, 기간별 탭은 계좌 태그 기반 고정 리스크 성향을 사용한다는
 * 점에서 서로 다른 API 응답(`GoalRecommendation`/`HorizonGoalRecommendation`)을 소비한다.
 * "전체" 탭은 목표 미설정 상태에서도 항상 노출해 설정 유도 문구를 보여준다. */
export default function RecommendationCard({ onApplied }: Props) {
  const queryClient = useQueryClient();

  const { data: overallData } = useQuery({
    queryKey: QUERY_KEYS.goalRecommendationOverall,
    queryFn: fetchOverallGoalRecommendation,
    staleTime: STALE_TIME.LONG,
  });

  const { data: horizonData } = useQuery({
    queryKey: QUERY_KEYS.goalRecommendationByHorizon,
    queryFn: fetchHorizonGoalRecommendations,
    staleTime: STALE_TIME.LONG,
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

  const { data: settingsData } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });
  const candidateCount = settingsData?.goal_candidate_tickers?.length ?? 0;

  const horizonRecommendations = horizonData?.recommendations ?? [];
  const availableHorizons = HORIZON_ORDER.filter((h) =>
    horizonRecommendations.some((r) => r.investment_horizon === h),
  );

  const [activeTab, setActiveTab] = useState<ActiveTab>("전체");
  const effectiveTab: ActiveTab =
    activeTab === "전체" || availableHorizons.includes(activeTab) ? activeTab : "전체";

  const taxTypesForHorizon = TAX_TYPE_ORDER.filter((t) =>
    horizonRecommendations.some((r) => r.investment_horizon === effectiveTab && r.tax_type === t),
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

  const applyHorizonMutation = useMutation({
    mutationFn: async () => {
      if (!activeHorizonRec || !horizonTargetPortfolio) throw new Error("추천 비중이 없습니다");
      await updatePortfolio(horizonTargetPortfolio.id, {
        items: normalizeWeights(activeHorizonRec.recommended_items),
      });
      return horizonTargetPortfolio.id;
    },
    onSuccess: async (portfolioId) => {
      setConfirmOpen(false);
      await invalidatePortfolioData(queryClient);
      onApplied?.(portfolioId);
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  const [managerOpen, setManagerOpen] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);

  // 최초 방문 시 백엔드가 후보를 시드하거나(seed) 세제유형 선호 지수에 맞는 큐레이션 ETF를 자동
  // 추가해 DB에 커밋할 수 있으므로, 이미 캐시된 settings 쿼리가 그 이전 값을 들고 있을 수 있다.
  // overall/horizon 두 조회는 응답 시간이 크게 달라(horizon은 최대 15개 조합을 순회해 훨씬 느림)
  // 한쪽만 트리거하면 늦게 끝나는 쪽의 커밋을 놓칠 수 있으므로, 각각 도착할 때 독립적으로 1회씩
  // settings를 재조회해 동기화한다.
  const overallSettingsSyncedRef = useRef(false);
  useEffect(() => {
    if (overallData && !overallSettingsSyncedRef.current) {
      overallSettingsSyncedRef.current = true;
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.settings });
    }
  }, [overallData, queryClient]);
  const horizonSettingsSyncedRef = useRef(false);
  useEffect(() => {
    if (horizonData && !horizonSettingsSyncedRef.current) {
      horizonSettingsSyncedRef.current = true;
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.settings });
    }
  }, [horizonData, queryClient]);

  if (!overallData) return null;

  const hasOverallRecommendation =
    overallData.is_configured && overallData.recommended_items.length > 0;
  const isCashEquivalentItem = (item: GoalRecommendationItem) =>
    item.ticker === CASH_EQUIVALENT_TICKER;

  return (
    <>
      <div className="rounded-xl border border-teal-200 dark:border-teal-800/50 bg-teal-50 dark:bg-teal-900/20 p-4 space-y-2">
        <div className="flex items-center gap-2">
          <Target size={13} className="text-teal-500 shrink-0" />
          <span className="text-xs font-semibold text-teal-700 dark:text-teal-400">추천 비중</span>
        </div>

        <div className="flex gap-1.5">
          {(["전체", ...availableHorizons] as ActiveTab[]).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
                tab === effectiveTab
                  ? "bg-teal-600 text-white"
                  : "bg-white dark:bg-gray-800 text-teal-600 dark:text-teal-400 border border-teal-200 dark:border-teal-800/50"
              }`}
            >
              {tab === "전체" ? "전체" : INVESTMENT_HORIZON_LABELS[tab]}
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
                className={`px-2 py-0.5 text-[11px] rounded-full border transition-colors ${
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
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {overallData.note ?? "목표금액·목표연도를 설정하면 추천을 받을 수 있습니다"}
            </p>
          ) : (
            <>
              {hasOverallRecommendation ? (
                <>
                  <p className="text-xs text-gray-600 dark:text-gray-300">
                    목표 달성에 필요한 연 수익률 {overallData.required_return_pct?.toFixed(1)}% —
                    아래 비중으로 조정하면 기대수익률 {overallData.expected_return_pct?.toFixed(1)}%
                    (최근 {overallData.cagr_lookback_years}년 CAGR 기준)
                    {overallData.expected_dividend_yield_pct != null &&
                      ` (배당수익률 약 ${overallData.expected_dividend_yield_pct.toFixed(1)}%)`}
                    를 기대할 수 있습니다.
                  </p>

                  <ul className="space-y-1">
                    {overallData.recommended_items.map((item) => (
                      <li
                        key={`${item.ticker}-${item.market}`}
                        className="flex items-center justify-between text-xs"
                      >
                        <span className="text-gray-700 dark:text-gray-300">
                          {item.name} <span className="text-gray-400">({item.ticker})</span>
                        </span>
                        <span className="font-medium text-teal-600 dark:text-teal-400">
                          {item.weight.toFixed(1)}%
                        </span>
                      </li>
                    ))}
                  </ul>

                  {overallData.note && (
                    <p className="text-xs text-amber-600 dark:text-amber-500 pt-1">
                      {overallData.note}
                    </p>
                  )}

                  <p className="text-xs text-teal-500 dark:text-teal-500 pt-1">
                    등록한 후보 종목 기준 참고용 제안 — 자동 반영되지 않습니다.
                  </p>

                  <div className="pt-2 border-t border-teal-200 dark:border-teal-800/50">
                    {targetPortfolios.length === 0 ? (
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        포트폴리오 탭에서 목표 포트폴리오를 지정하면 추천 비중을 바로 적용할 수
                        있어요.
                      </p>
                    ) : (
                      <div className="flex items-center gap-2 flex-wrap">
                        {targetPortfolios.length > 1 && (
                          <select
                            value={selectedOverallTargetId}
                            onChange={(e) => setSelectedOverallTargetId(e.target.value)}
                            className="text-xs border border-teal-200 dark:border-teal-800/50 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-teal-500"
                          >
                            <option value="">포트폴리오 선택</option>
                            {targetPortfolios.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.name}
                              </option>
                            ))}
                          </select>
                        )}
                        <button
                          type="button"
                          disabled={
                            (targetPortfolios.length > 1 && !selectedOverallTargetId) ||
                            applyOverallMutation.isPending
                          }
                          onClick={() => setConfirmOpen(true)}
                          className="flex items-center gap-1 text-xs font-medium text-white bg-teal-600 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed px-3 py-1.5 rounded-lg transition-colors"
                        >
                          {applyOverallMutation.isPending ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <Target size={12} />
                          )}
                          {targetPortfolios.length === 1
                            ? `${targetPortfolios[0].name}에 적용`
                            : "목표 포트폴리오에 적용"}
                        </button>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {overallData.note ?? "추천을 계산할 수 없습니다 — 후보 ETF를 등록해주세요"}
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
              {activeHorizonRec.recommended_items.length > 0 &&
                activeHorizonRec.expected_return_pct != null &&
                ` · 기대수익률 ${activeHorizonRec.expected_return_pct.toFixed(1)}%`}
            </p>

            {activeHorizonRec.recommended_items.length > 0 ? (
              <>
                <ul className="space-y-1">
                  {activeHorizonRec.recommended_items.map((item) => (
                    <li
                      key={`${item.ticker}-${item.market}`}
                      className="flex items-center justify-between text-xs"
                    >
                      <span className="text-gray-700 dark:text-gray-300">
                        {item.name}
                        {!isCashEquivalentItem(item) && (
                          <span className="text-gray-400"> ({item.ticker})</span>
                        )}
                      </span>
                      <span className="font-medium text-teal-600 dark:text-teal-400">
                        {item.weight.toFixed(1)}%
                      </span>
                    </li>
                  ))}
                </ul>
                {activeHorizonRec.note && (
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {activeHorizonRec.note}
                  </p>
                )}
              </>
            ) : (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {activeHorizonRec.note ?? "추천을 계산할 수 없습니다"}
              </p>
            )}

            {activeHorizonRec.recommended_items.length > 0 &&
              activeHorizonRec.includes_cash_equivalent && (
                <p className="text-xs text-gray-500 dark:text-gray-400 pt-2 border-t border-teal-200 dark:border-teal-800/50">
                  현금성 자산(CMA·파킹통장 등)이 포함된 추천은 자동 적용할 수 없어요 — 실제 계좌에서
                  해당 비중만큼 현금성 자산으로 배분해주세요.
                </p>
              )}

            {activeHorizonRec.recommended_items.length > 0 &&
              !activeHorizonRec.includes_cash_equivalent && (
                <div className="pt-2 border-t border-teal-200 dark:border-teal-800/50">
                  {horizonTargetPortfolio ? (
                    <button
                      type="button"
                      disabled={applyHorizonMutation.isPending}
                      onClick={() => setConfirmOpen(true)}
                      className="flex items-center gap-1 text-xs font-medium text-white bg-teal-600 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed px-3 py-1.5 rounded-lg transition-colors"
                    >
                      {applyHorizonMutation.isPending ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Target size={12} />
                      )}
                      {horizonTargetPortfolio.name}에 적용
                    </button>
                  ) : (
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      포트폴리오 탭에서 이 기간·계좌유형에 해당하는 계좌를 태그하고 목표
                      포트폴리오로 지정하면 추천 비중을 바로 적용할 수 있어요.
                    </p>
                  )}
                </div>
              )}
          </>
        ) : null}

        <div className="pt-2 border-t border-teal-200 dark:border-teal-800/50 flex items-center gap-3">
          <button
            type="button"
            onClick={() => setManagerOpen(true)}
            className="flex items-center gap-1 text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700"
          >
            <Plus size={12} />
            후보 ETF 관리{candidateCount > 0 && ` (${candidateCount})`}
          </button>
          <button
            type="button"
            onClick={() => setOptionsOpen(true)}
            className="flex items-center gap-1 text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700"
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
          message={`${overallConfirmTarget.name}의 목표 비중이 추천 비중으로 즉시 업데이트되고, 리밸런싱 실행 화면이 열립니다. 계속하시겠습니까?`}
          confirmLabel="적용"
          danger={false}
          onConfirm={() => applyOverallMutation.mutate(overallConfirmTarget.id)}
          onCancel={() => setConfirmOpen(false)}
        />
      )}

      {confirmOpen && effectiveTab !== "전체" && horizonTargetPortfolio && (
        <ConfirmModal
          message={`${horizonTargetPortfolio.name}의 목표 비중이 추천 비중으로 즉시 업데이트되고, 리밸런싱 실행 화면이 열립니다. 계속하시겠습니까?`}
          confirmLabel="적용"
          danger={false}
          onConfirm={() => applyHorizonMutation.mutate()}
          onCancel={() => setConfirmOpen(false)}
        />
      )}
    </>
  );
}
