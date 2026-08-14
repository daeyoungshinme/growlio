import type { SettingsData } from "@/api/settings";

/** "정기 리포트·요약" 그룹 필드 — SettingsPage/NotificationSettingsPage 요약 카운트 공용 정의 */
export const REPORT_ALERT_FIELDS = [
  "monthly_report_enabled",
  "year_end_tax_reminder_enabled",
  "recommendation_drift_alert_enabled",
] as const satisfies readonly (keyof SettingsData)[];

/** "즉시 알림" 그룹 필드 */
export const INSTANT_ALERT_FIELDS = [
  "goal_achievement_alerts_enabled",
] as const satisfies readonly (keyof SettingsData)[];

export function countEnabled(values: readonly boolean[]): number {
  return values.filter(Boolean).length;
}
