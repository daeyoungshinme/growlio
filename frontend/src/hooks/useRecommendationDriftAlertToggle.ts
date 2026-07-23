import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchSettings, updateRecommendationDriftAlert } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateRecommendationDriftAlertData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

/** 매주 월요일 09:15 KST 발송되는 "추천 비중이 달라졌어요" 알림(이메일·푸시) 수신 on/off. */
export function useRecommendationDriftAlertToggle() {
  const qc = useQueryClient();
  const { data: settings } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });

  const toggleMut = useMutation({
    mutationFn: (enabled: boolean) => updateRecommendationDriftAlert(enabled),
    onSuccess: () => {
      void invalidateRecommendationDriftAlertData(qc);
    },
    onError: (e) => toast(extractErrorMessage(e, "설정 저장에 실패했습니다"), "error"),
  });

  return {
    enabled: settings?.recommendation_drift_alert_enabled ?? false,
    toggle: (enabled: boolean) => toggleMut.mutate(enabled),
    isPending: toggleMut.isPending,
  };
}
