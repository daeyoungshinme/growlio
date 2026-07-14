import { useState } from "react";
import { Loader2, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchIndexRegion } from "@/api/assets";
import {
  fetchSettings,
  updateGoalCandidateTickers,
  type AssetClass,
  type GoalCandidateTicker,
  type IndexRegion,
} from "@/api/settings";
import { DOMESTIC_MARKETS } from "@/constants";
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

const ASSET_CLASS_LABELS: Record<AssetClass, string> = {
  EQUITY: "주식",
  BOND: "채권",
  CASH: "현금성",
};

interface Props {
  onClose: () => void;
}

/** 목표 역산 추천 카드의 후보 ETF 검색·추가·삭제 UI — 카드 depth 축소를 위해 별도 모달로 분리됨. */
export default function GoalCandidateManagerModal({ onClose }: Props) {
  const queryClient = useQueryClient();
  const [candidateQuery, setCandidateQuery] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [pendingCandidates, setPendingCandidates] = useState<GoalCandidateTicker[] | null>(null);
  const [isResolvingRegion, setIsResolvingRegion] = useState(false);
  const { suggestions, isSearching, search, clearSuggestions } = useStockSearch();

  // 모달을 여는 시점에 백엔드가 방금 자동 추가한 큐레이션 ETF가 캐시에 아직 반영되지 않았을 수
  // 있다 — refetchOnMount로 STALE_TIME 캐시와 무관하게 항상 최신 DB 상태를 가져와, 전체교체 저장이
  // 스테일 데이터로 그 추가분을 지워버리는 것을 방지한다.
  const { data: settingsData } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
    refetchOnMount: "always",
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

  const addCandidate = async (s: {
    ticker: string;
    name: string;
    market: string;
    asset_class?: AssetClass;
    index_region?: IndexRegion;
  }) => {
    setCandidateQuery("");
    clearSuggestions();
    setShowSuggestions(false);
    if (candidates.some((c) => c.ticker === s.ticker && c.market === s.market)) return;
    if (candidates.length >= MAX_CANDIDATE_TICKERS) {
      toast(`후보 ETF는 최대 ${MAX_CANDIDATE_TICKERS}개까지 등록할 수 있습니다`, "error");
      return;
    }

    const assetClass = s.asset_class ?? "EQUITY";
    let indexRegion = s.index_region;
    // 해외거래소 상장·비주식 후보는 검색 결과의 시장구분 기반 제안값으로 이미 충분 — KRX 상장
    // 주식만 실제 추종지수(국내/해외)를 서버에서 조회해 정확히 판별한다.
    if (assetClass === "EQUITY" && DOMESTIC_MARKETS.includes(s.market.toUpperCase())) {
      setIsResolvingRegion(true);
      try {
        indexRegion = (await fetchIndexRegion(s.ticker, s.market)).index_region;
      } catch {
        // 조회 실패 시 검색 결과의 기본 제안값을 그대로 사용
      } finally {
        setIsResolvingRegion(false);
      }
    }

    setPendingCandidates((prev) => {
      const base = prev ?? savedCandidates;
      if (base.some((c) => c.ticker === s.ticker && c.market === s.market)) return prev;
      return [
        ...base,
        {
          ticker: s.ticker,
          name: s.name,
          market: s.market,
          asset_class: assetClass,
          index_region: indexRegion,
        },
      ];
    });
  };

  const removeCandidate = (ticker: string, market: string) => {
    setPendingCandidates(candidates.filter((c) => !(c.ticker === ticker && c.market === market)));
  };

  const changeAssetClass = (ticker: string, market: string, assetClass: AssetClass) => {
    setPendingCandidates(
      candidates.map((c) =>
        c.ticker === ticker && c.market === market ? { ...c, asset_class: assetClass } : c,
      ),
    );
  };

  return (
    <Modal onClose={onClose} title="후보 ETF 관리" size="sm">
      <div className="flex-1 overflow-y-auto overscroll-contain p-4 space-y-3">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          목표 달성 추천 비중 계산에 함께 고려할 ETF 후보를 등록합니다. ISA·연금저축·IRP 계좌는
          해외지수 추종 ETF를, 일반 계좌는 국내지수 추종 종목·ETF를 기간별 추천에서 우선 반영합니다
          — 추종지수 지역은 추가 시 자동으로 판별되며 별도 설정이 필요 없습니다. 자산군은 추가 시
          자동 제안되며, 정확하지 않으면 직접 수정할 수 있습니다.
        </p>

        {candidates.length > 0 && (
          <ul className="space-y-1">
            {candidates.map((c) => (
              <li
                key={`${c.ticker}-${c.market}`}
                className="flex items-center gap-1.5 text-xs bg-purple-50 dark:bg-gray-800 border border-purple-200 dark:border-purple-800/50 rounded-full pl-2 pr-1 py-0.5"
              >
                <span className="text-gray-700 dark:text-gray-300 truncate">
                  {c.name} <span className="text-gray-400">({c.ticker})</span>
                </span>
                <div className="ml-auto flex items-center gap-1 shrink-0">
                  <select
                    value={c.asset_class ?? "EQUITY"}
                    onChange={(e) =>
                      changeAssetClass(c.ticker, c.market, e.target.value as AssetClass)
                    }
                    aria-label={`${c.name} 자산군`}
                    className="shrink-0 text-xs bg-transparent border border-purple-200 dark:border-purple-800/50 rounded-full px-1.5 py-0.5 text-purple-600 dark:text-purple-400 focus:outline-none focus:ring-1 focus:ring-purple-500"
                  >
                    {Object.entries(ASSET_CLASS_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  onClick={() => removeCandidate(c.ticker, c.market)}
                  className="p-0.5 text-gray-400 hover:text-red-500 rounded-full shrink-0"
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
          {(isSearching || isResolvingRegion) && (
            <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">
              {isResolvingRegion ? "확인 중..." : "검색 중..."}
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
                  onMouseDown={() => void addCandidate(s)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      void addCandidate(s);
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
