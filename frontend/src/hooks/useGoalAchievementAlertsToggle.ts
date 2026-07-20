import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchSettings, updateGoalAchievementAlerts } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateGoalAchievementAlertsData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

/** 자산/입금/배당 목표 달성 알림(이메일·푸시) on/off. */
export function useGoalAchievementAlertsToggle() {
  const qc = useQueryClient();
  const { data: settings } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });

  const toggleMut = useMutation({
    mutationFn: (enabled: boolean) => updateGoalAchievementAlerts(enabled),
    onSuccess: () => {
      void invalidateGoalAchievementAlertsData(qc);
    },
    onError: (e) => toast(extractErrorMessage(e, "설정 저장에 실패했습니다"), "error"),
  });

  return {
    enabled: settings?.goal_achievement_alerts_enabled ?? true,
    toggle: (enabled: boolean) => toggleMut.mutate(enabled),
    isPending: toggleMut.isPending,
  };
}
