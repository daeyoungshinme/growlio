import { useState } from "react";
import { Loader2, Plus, Target, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchOverallGoalRecommendation, type GoalRecommendationItem } from "@/api/rebalancing";
import {
  fetchSettings,
  updateGoalCandidateTickers,
  type GoalCandidateTicker,
} from "@/api/settings";
import { fetchPortfolios, updatePortfolio } from "@/api/portfolios";
import { fetchAccounts } from "@/api/assets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { SEARCH_DROPDOWN_HIDE_DELAY } from "@/constants/timers";
import { useStockSearch } from "@/hooks/useStockSearch";
import { invalidateGoalCandidateData, invalidatePortfolioData } from "@/utils/queryInvalidation";
import { getPortfolioTargetState } from "@/utils/portfolio";
import { isStockAccount } from "@/utils/accounts";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import ConfirmModal from "@/components/common/ConfirmModal";

const MAX_CANDIDATE_TICKERS = 10;

function normalizeWeights(items: GoalRecommendationItem[]) {
  const normalized = items.map((i) => ({ ...i, weight: Math.round(i.weight * 10) / 10 }));
  const diff = Math.round((100 - normalized.reduce((s, i) => s + i.weight, 0)) * 10) / 10;
  if (normalized.length > 0 && diff !== 0) normalized[normalized.length - 1].weight += diff;
  return normalized;
}

interface Props {
  /** 부모가 이미 카드 간 간격을 제공하는 경우(e.g. 진단 탭의 flex gap) true로 넘겨 자체 상단 여백을 제거한다. */
  noTopMargin?: boolean;
  /** 추천 비중을 목표 포트폴리오에 저장한 뒤 호출된다 — 부모가 화면 전환(포트폴리오 탭 이동 등)을 담당한다. */
  onApplied?: (portfolioId: string) => void;
}

/** 목표 역산 추천(로드맵 A 3단계) — 전체 자산 기준으로 추천 비중이 있을 때만 카드를 표시한다. */
export default function GoalRecommendationCard({ noTopMargin = false, onApplied }: Props) {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: QUERY_KEYS.goalRecommendationOverall,
    queryFn: fetchOverallGoalRecommendation,
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

  const targetPortfolios = portfolios.filter(
    (p) => getPortfolioTargetState(p, stockAccounts) !== "none",
  );

  const [selectedTargetId, setSelectedTargetId] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);

  const applyMutation = useMutation({
    mutationFn: async (portfolioId: string) => {
      if (!data) throw new Error("추천 비중이 없습니다");
      await updatePortfolio(portfolioId, { items: normalizeWeights(data.recommended_items) });
      return portfolioId;
    },
    onSuccess: async (portfolioId) => {
      setConfirmOpen(false);
      await invalidatePortfolioData(queryClient);
      onApplied?.(portfolioId);
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  const confirmTarget =
    targetPortfolios.find((p) => p.id === selectedTargetId) ?? targetPortfolios[0];

  const [managerOpen, setManagerOpen] = useState(false);
  const [candidateQuery, setCandidateQuery] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [pendingCandidates, setPendingCandidates] = useState<GoalCandidateTicker[] | null>(null);
  const { suggestions, isSearching, search, clearSuggestions } = useStockSearch();

  const { data: settingsData } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });

  const savedCandidates = settingsData?.goal_candidate_tickers ?? [];
  const candidates = pendingCandidates ?? savedCandidates;

  const saveMutation = useMutation({
    mutationFn: updateGoalCandidateTickers,
    onSuccess: async () => {
      toast("후보 ETF 목록이 저장되었습니다", "success");
      setPendingCandidates(null);
      await invalidateGoalCandidateData(queryClient);
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  const addCandidate = (s: { ticker: string; name: string; market: string }) => {
    setCandidateQuery("");
    clearSuggestions();
    setShowSuggestions(false);
    if (candidates.some((c) => c.ticker === s.ticker && c.market === s.market)) return;
    if (candidates.length >= MAX_CANDIDATE_TICKERS) {
      toast(`후보 ETF는 최대 ${MAX_CANDIDATE_TICKERS}개까지 등록할 수 있습니다`, "error");
      return;
    }
    setPendingCandidates([...candidates, { ticker: s.ticker, name: s.name, market: s.market }]);
  };

  const removeCandidate = (ticker: string, market: string) => {
    setPendingCandidates(candidates.filter((c) => !(c.ticker === ticker && c.market === market)));
  };

  if (!data || !data.is_configured || data.recommended_items.length === 0) return null;

  return (
    <>
      <div
        className={`${noTopMargin ? "" : "mt-3"} rounded-xl border border-purple-200 dark:border-purple-800/50 bg-purple-50 dark:bg-purple-900/20 p-4 space-y-2`}
      >
        <div className="flex items-center gap-2">
          <Target size={13} className="text-purple-500 shrink-0" />
          <span className="text-xs font-semibold text-purple-700 dark:text-purple-400">
            목표 달성 추천 비중 (전체 자산 기준)
          </span>
        </div>

        <p className="text-xs text-gray-600 dark:text-gray-300">
          목표 달성에 필요한 연 수익률 {data.required_return_pct?.toFixed(1)}% — 아래 비중으로
          조정하면 기대수익률 {data.expected_return_pct?.toFixed(1)}%
          {data.expected_dividend_yield_pct != null &&
            ` (배당수익률 약 ${data.expected_dividend_yield_pct.toFixed(1)}%)`}
          를 기대할 수 있습니다.
        </p>

        <ul className="space-y-1">
          {data.recommended_items.map((item) => (
            <li
              key={`${item.ticker}-${item.market}`}
              className="flex items-center justify-between text-xs"
            >
              <span className="text-gray-700 dark:text-gray-300">
                {item.name} <span className="text-gray-400">({item.ticker})</span>
              </span>
              <span className="font-medium text-purple-600 dark:text-purple-400">
                {item.weight.toFixed(1)}%
              </span>
            </li>
          ))}
        </ul>

        <p className="text-xs text-purple-500 dark:text-purple-500 pt-1">
          큐레이션 ETF 포함 참고용 제안 — 자동 반영되지 않습니다.
        </p>

        <div className="pt-2 border-t border-purple-200 dark:border-purple-800/50">
          {targetPortfolios.length === 0 ? (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              포트폴리오 탭에서 목표 포트폴리오를 지정하면 추천 비중을 바로 적용할 수 있어요.
            </p>
          ) : (
            <div className="flex items-center gap-2 flex-wrap">
              {targetPortfolios.length > 1 && (
                <select
                  value={selectedTargetId}
                  onChange={(e) => setSelectedTargetId(e.target.value)}
                  className="text-xs border border-purple-200 dark:border-purple-800/50 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-purple-500"
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
                  (targetPortfolios.length > 1 && !selectedTargetId) || applyMutation.isPending
                }
                onClick={() => setConfirmOpen(true)}
                className="flex items-center gap-1 text-xs font-medium text-white bg-purple-600 hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed px-3 py-1.5 rounded-lg transition-colors"
              >
                {applyMutation.isPending ? (
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

        <div className="pt-2 border-t border-purple-200 dark:border-purple-800/50">
          <button
            type="button"
            onClick={() => setManagerOpen((v) => !v)}
            className="flex items-center gap-1 text-xs font-medium text-purple-600 dark:text-purple-400 hover:text-purple-700"
          >
            <Plus size={12} />
            후보 ETF 관리{candidates.length > 0 && ` (${candidates.length})`}
          </button>

          {managerOpen && (
            <div className="mt-2 space-y-2">
              {candidates.length > 0 && (
                <ul className="flex flex-wrap gap-1.5">
                  {candidates.map((c) => (
                    <li
                      key={`${c.ticker}-${c.market}`}
                      className="flex items-center gap-1 text-xs bg-white dark:bg-gray-800 border border-purple-200 dark:border-purple-800/50 rounded-full pl-2 pr-1 py-0.5"
                    >
                      <span className="text-gray-700 dark:text-gray-300">
                        {c.name} <span className="text-gray-400">({c.ticker})</span>
                      </span>
                      <button
                        type="button"
                        onClick={() => removeCandidate(c.ticker, c.market)}
                        className="p-0.5 text-gray-400 hover:text-red-500 rounded-full"
                        aria-label={`${c.name} 제거`}
                      >
                        <X size={10} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div className="relative">
                <input
                  value={candidateQuery}
                  onChange={(e) => {
                    const v = e.target.value;
                    setCandidateQuery(v);
                    setShowSuggestions(true);
                    if (!v.trim()) {
                      clearSuggestions();
                      return;
                    }
                    search(v);
                  }}
                  onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                  onBlur={() =>
                    setTimeout(() => setShowSuggestions(false), SEARCH_DROPDOWN_HIDE_DELAY)
                  }
                  placeholder="추가할 ETF 종목명 또는 코드 검색"
                  className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                {isSearching && (
                  <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">
                    검색 중...
                  </span>
                )}
                {showSuggestions && suggestions.length > 0 && (
                  <ul
                    role="listbox"
                    aria-label="ETF 검색 결과"
                    className="absolute z-20 left-0 right-0 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg mt-0.5 max-h-40 overflow-y-auto"
                  >
                    {suggestions.map((s) => (
                      <li
                        key={`${s.ticker}-${s.market}`}
                        role="option"
                        aria-selected={false}
                        tabIndex={0}
                        className="px-2.5 py-1.5 hover:bg-purple-50 dark:hover:bg-purple-950 cursor-pointer text-xs flex items-center gap-2 focus:bg-purple-50 dark:focus:bg-purple-950 focus:outline-none"
                        onMouseDown={() => addCandidate(s)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            addCandidate(s);
                          }
                        }}
                      >
                        <span className="font-medium text-purple-700 dark:text-purple-400">
                          {s.ticker}
                        </span>
                        <span className="text-gray-700 dark:text-gray-300">{s.name}</span>
                        <span className="text-xs text-gray-400 ml-auto">{s.market}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {pendingCandidates !== null && (
                <div className="flex justify-end">
                  <button
                    type="button"
                    disabled={saveMutation.isPending}
                    onClick={() => saveMutation.mutate(candidates)}
                    className="flex items-center gap-1 text-xs font-medium text-white bg-purple-600 hover:bg-purple-700 disabled:opacity-50 px-3 py-1.5 rounded-lg transition-colors"
                  >
                    {saveMutation.isPending && <Loader2 size={12} className="animate-spin" />}
                    저장
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {confirmOpen && confirmTarget && (
        <ConfirmModal
          message={`${confirmTarget.name}의 목표 비중이 추천 비중으로 즉시 업데이트되고, 리밸런싱 실행 화면이 열립니다. 계속하시겠습니까?`}
          confirmLabel="적용"
          danger={false}
          onConfirm={() => applyMutation.mutate(confirmTarget.id)}
          onCancel={() => setConfirmOpen(false)}
        />
      )}
    </>
  );
}
