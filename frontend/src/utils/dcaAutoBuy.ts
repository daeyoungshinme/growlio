import type { RebalancingAlert } from "@/api/alerts";

/** 리밸런싱 알림 설정이 "정기 적립식 자동매수" 형태(매월 특정일 · 무조건 실행 · 자동 · 매수만)와
 * 일치하는지 판정한다. threshold_pct는 사용자가 나중에 손으로 조정했을 수 있어 비교 대상에서
 * 제외한다 — 나머지 4개 필드가 이 조합이면 화면에는 "정기 적립식 자동매수"로 보여준다. */
export function isDcaAutoBuyPreset(alert: RebalancingAlert | null | undefined): boolean {
  if (!alert) return false;
  return (
    alert.schedule_type === "MONTHLY" &&
    alert.trigger_condition === "SCHEDULE_ONLY" &&
    alert.mode === "AUTO" &&
    alert.strategy === "BUY_ONLY"
  );
}

/** "매월 25일 자동매수 중" 같은 한 줄 요약. isDcaAutoBuyPreset(alert)가 false면 빈 문자열을 반환한다. */
export function describeDcaAutoBuy(alert: RebalancingAlert | null | undefined): string {
  if (!isDcaAutoBuyPreset(alert) || !alert) return "";
  const day = alert.schedule_day_of_month ?? 1;
  return `매월 ${day}일 자동매수 중`;
}
