import { useSettingsToggle } from "@/hooks/useSettingsToggle";
import { updateGoalAchievementAlerts } from "@/api/settings";

/** 자산/입금/배당 목표 달성 알림(이메일·푸시) on/off. */
export const useGoalAchievementAlertsToggle = () =>
  useSettingsToggle({
    field: "goal_achievement_alerts_enabled",
    defaultValue: true,
    mutationFn: (enabled: boolean) => updateGoalAchievementAlerts(enabled),
  });
