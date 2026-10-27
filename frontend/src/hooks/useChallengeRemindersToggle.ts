import { useSettingsToggle } from "@/hooks/useSettingsToggle";
import { updateChallengeReminders } from "@/api/settings";

/** 적립 챌린지 독려(매월 25일)·월간 결산(매월 1일) 알림 on/off — 옵트인(기본 OFF). */
export const useChallengeRemindersToggle = () =>
  useSettingsToggle({
    field: "challenge_reminders_enabled",
    defaultValue: false,
    mutationFn: (enabled: boolean) => updateChallengeReminders(enabled),
  });
