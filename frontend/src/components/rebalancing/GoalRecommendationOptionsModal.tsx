import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchSettings,
  updateGoalRecommendationOptions,
  type GoalRiskTolerance,
} from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateGoalRecommendationData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import Modal from "@/components/common/Modal";

const RISK_TOLERANCE_OPTIONS: { value: GoalRiskTolerance; label: string }[] = [
  { value: "CONSERVATIVE", label: "보수적 (목표치 그대로)" },
  { value: "BALANCED", label: "중립 (+1.0%p 여유)" },
  { value: "AGGRESSIVE", label: "공격적 (+2.5%p 여유)" },
];

const CAGR_LOOKBACK_OPTIONS = [3, 5, 10];

interface Props {
  onClose: () => void;
}

/** 목표 역산 추천 엔진 튜닝 설정(리스크 성향/종목당 최대비중/CAGR 산출기간) — 후보 ETF 관리와는
 * 별도 모달로 분리해 각 모달의 책임을 단순하게 유지한다. */
export default function GoalRecommendationOptionsModal({ onClose }: Props) {
  const queryClient = useQueryClient();

  const { data: settingsData } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });

  const [riskTolerance, setRiskTolerance] = useState<GoalRiskTolerance | null>(null);
  const [maxWeightPct, setMaxWeightPct] = useState<number | null>(null);
  const [cagrLookbackYears, setCagrLookbackYears] = useState<number | null>(null);
  const [shortTermEquityFloorPct, setShortTermEquityFloorPct] = useState<number | null>(null);

  const savedRiskTolerance = settingsData?.goal_risk_tolerance ?? "CONSERVATIVE";
  const savedMaxWeightPct = settingsData?.goal_max_weight_pct ?? 40.0;
  const savedCagrLookbackYears = settingsData?.goal_cagr_lookback_years ?? 10;
  const savedShortTermEquityFloorPct = settingsData?.goal_short_term_equity_floor_pct ?? 80.0;

  const currentRiskTolerance = riskTolerance ?? savedRiskTolerance;
  const currentMaxWeightPct = maxWeightPct ?? savedMaxWeightPct;
  const currentCagrLookbackYears = cagrLookbackYears ?? savedCagrLookbackYears;
  const currentShortTermEquityFloorPct = shortTermEquityFloorPct ?? savedShortTermEquityFloorPct;

  const isDirty =
    currentRiskTolerance !== savedRiskTolerance ||
    currentMaxWeightPct !== savedMaxWeightPct ||
    currentCagrLookbackYears !== savedCagrLookbackYears ||
    currentShortTermEquityFloorPct !== savedShortTermEquityFloorPct;

  const saveMutation = useMutation({
    mutationFn: updateGoalRecommendationOptions,
    onSuccess: async () => {
      toast("추천 설정이 저장되었습니다", "success");
      await invalidateGoalRecommendationData(queryClient);
      onClose();
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  return (
    <Modal onClose={onClose} title="추천 설정" size="sm">
      <div className="flex-1 overflow-y-auto overscroll-contain p-4 space-y-4">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          목표 달성 추천 비중을 계산하는 방식을 조정합니다. 저장하지 않으면 기존 설정이 유지됩니다.
        </p>

        <div>
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
            리스크 성향
          </label>
          <select
            value={currentRiskTolerance}
            onChange={(e) => setRiskTolerance(e.target.value as GoalRiskTolerance)}
            className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            {RISK_TOLERANCE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <p className="text-xs text-gray-400 mt-1">
            목표 달성에 필요한 최소 수익률보다 더 높은 수익률을 목표로 삼을수록 변동성도 커집니다.
          </p>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
            종목당 최대 비중
          </label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              inputMode="numeric"
              min={10}
              max={100}
              step={5}
              value={currentMaxWeightPct}
              onChange={(e) => setMaxWeightPct(Number(e.target.value))}
              className="w-24 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <span className="text-xs text-gray-500 dark:text-gray-400">% (10~100)</span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            특정 종목에 쏠리지 않는 조합이 추천된 경우라면 상한을 낮춰도 비중이 그대로일 수 있어요.
          </p>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
            기대수익률(CAGR) 산출 기간
          </label>
          <select
            value={currentCagrLookbackYears}
            onChange={(e) => setCagrLookbackYears(Number(e.target.value))}
            className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            {CAGR_LOOKBACK_OPTIONS.map((years) => (
              <option key={years} value={years}>
                최근 {years}년
              </option>
            ))}
          </select>
          <p className="text-xs text-gray-400 mt-1">
            보수적 성향에서는 변동성이 가장 낮은 조합을 그대로 추천하므로 기간을 바꿔도 비중이
            그대로일 수 있어요.
          </p>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
            단기(최대 3년) 목표 최소 주식 비중
          </label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              inputMode="numeric"
              min={0}
              max={100}
              step={5}
              value={currentShortTermEquityFloorPct}
              onChange={(e) => setShortTermEquityFloorPct(Number(e.target.value))}
              className="w-24 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <span className="text-xs text-gray-500 dark:text-gray-400">% (0~100)</span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            나머지 비중은 채권/현금성 ETF 및 현금성 자산(CMA·파킹통장)으로 채워집니다. 0으로
            설정하면 이 하한 없이 계산됩니다.
          </p>
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            닫기
          </button>
          {isDirty && (
            <button
              type="button"
              disabled={saveMutation.isPending}
              onClick={() =>
                saveMutation.mutate({
                  risk_tolerance: currentRiskTolerance,
                  max_weight_pct: currentMaxWeightPct,
                  cagr_lookback_years: currentCagrLookbackYears,
                  short_term_equity_floor_pct: currentShortTermEquityFloorPct,
                })
              }
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
