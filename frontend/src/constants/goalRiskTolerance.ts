import type { GoalRiskTolerance } from "@/api/settings";

/** 목표 역산 추천 엔진의 리스크 성향 3단계 — `GoalRecommendationOptionsModal.tsx`(추천 설정)와
 * `GoalSettingWizard.tsx`(온보딩) 양쪽에서 공유해 레이블이 서로 어긋나지 않게 한다. */
export const RISK_TOLERANCE_OPTIONS: { value: GoalRiskTolerance; label: string }[] = [
  { value: "CONSERVATIVE", label: "보수적 (목표치 그대로)" },
  { value: "BALANCED", label: "중립 (+1.0%p 여유)" },
  { value: "AGGRESSIVE", label: "공격적 (+2.5%p 여유)" },
];
