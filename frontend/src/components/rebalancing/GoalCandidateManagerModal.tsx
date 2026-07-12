import { useState } from "react";
import { Loader2, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchSettings,
  updateGoalCandidateTickers,
  type GoalCandidateTicker,
} from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { SEARCH_DROPDOWN_HIDE_DELAY } from "@/constants/timers";
import { useStockSearch } from "@/hooks/useStockSearch";
import { invalidateGoalRecommendationData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import Modal from "@/components/common/Modal";

// backend app/services/recommendation_universe.py의 MAX_GOAL_CANDIDATE_TICKERS와 동일하게 유지
const MAX_CANDIDATE_TICKERS = 20;

interface Props {
  onClose: () => void;
}

/** 목표 역산 추천 카드의 후보 ETF 검색·추가·삭제 UI — 카드 depth 축소를 위해 별도 모달로 분리됨. */
export default function GoalCandidateManagerModal({ onClose }: Props) {
  const queryClient = useQueryClient();
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
      await invalidateGoalRecommendationData(queryClient);
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

  return (
    <Modal onClose={onClose} title="후보 ETF 관리" size="sm">
      <div className="flex-1 overflow-y-auto overscroll-contain p-4 space-y-3">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          목표 달성 추천 비중 계산에 함께 고려할 ETF 후보를 등록합니다.
        </p>

        {candidates.length > 0 && (
          <ul className="flex flex-wrap gap-1.5">
            {candidates.map((c) => (
              <li
                key={`${c.ticker}-${c.market}`}
                className="flex items-center gap-1 text-xs bg-purple-50 dark:bg-gray-800 border border-purple-200 dark:border-purple-800/50 rounded-full pl-2 pr-1 py-0.5"
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
            onBlur={() => setTimeout(() => setShowSuggestions(false), SEARCH_DROPDOWN_HIDE_DELAY)}
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

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            닫기
          </button>
          {pendingCandidates !== null && (
            <button
              type="button"
              disabled={saveMutation.isPending}
              onClick={() => saveMutation.mutate(candidates)}
              className="flex items-center gap-1 text-xs font-medium text-white bg-purple-600 hover:bg-purple-700 disabled:opacity-50 px-3 py-1.5 rounded-lg transition-colors"
            >
              {saveMutation.isPending && <Loader2 size={12} className="animate-spin" />}
              저장
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
