import { useSettingsToggle } from "@/hooks/useSettingsToggle";
import { updateRecommendationDriftAlert } from "@/api/settings";

/** 매주 월요일 09:15 KST 발송되는 "추천 비중이 달라졌어요" 알림(이메일·푸시) 수신 on/off. */
export const useRecommendationDriftAlertToggle = () =>
  useSettingsToggle({
    field: "recommendation_drift_alert_enabled",
    defaultValue: false,
    mutationFn: (enabled: boolean) => updateRecommendationDriftAlert(enabled),
  });
