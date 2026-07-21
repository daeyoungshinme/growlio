/** 목표 설정 마법사의 "필요 연수익률" 결과를 사람이 읽는 톤으로 분류 — 순수 UI 언어 규칙, 백엔드 계산과 무관 */

export interface GoalFeasibilityBand {
  label: string;
  cls: string;
  description: string;
}

const IMPOSSIBLE_BAND: GoalFeasibilityBand = {
  label: "매우 어려운 목표",
  cls: "bg-red-50 dark:bg-red-950 text-red-600 dark:text-red-400",
  description: "목표금액을 낮추거나 기간을 늘리거나 적립액을 높여보세요.",
};

export function classifyGoalFeasibility(requiredReturnPct: number | null): GoalFeasibilityBand {
  if (requiredReturnPct === null) return IMPOSSIBLE_BAND;
  if (requiredReturnPct <= 6) {
    return {
      label: "안정적인 목표",
      cls: "bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400",
      description: "일반적인 자산배분으로도 무난히 도전해볼 수 있는 수준입니다.",
    };
  }
  if (requiredReturnPct <= 12) {
    return {
      label: "도전적인 목표",
      cls: "bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400",
      description: "주식 비중을 높인 적극적인 포트폴리오가 필요할 수 있어요.",
    };
  }
  return {
    label: "매우 공격적인 목표",
    cls: "bg-orange-50 dark:bg-orange-950 text-orange-600 dark:text-orange-400",
    description: "높은 변동성을 감수해야 하는 수준이에요. 조건을 조정하는 것도 고려해보세요.",
  };
}
