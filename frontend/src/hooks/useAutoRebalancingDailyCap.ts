import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchSettings, updateAutoRebalancingDailyCap } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

/** AUTO 리밸런싱 유저 단위 하루 합산 거래한도 조회/저장. `useSettingsToggle`(boolean 전용)과 같은 구조의
 * 숫자 버전 — 값이 null이면 무제한이며, 백엔드 게이트(`plan_generation.py`)가 이 값을 넘는 AUTO 실행을 보류한다. */
export function useAutoRebalancingDailyCap() {
  const qc = useQueryClient();
  const { data: settings, isLoading } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });

  const mutation = useMutation({
    mutationFn: updateAutoRebalancingDailyCap,
    onSuccess: (_data, value) => {
      toast(
        value == null ? "하루 거래한도를 해제했습니다" : "하루 거래한도가 저장되었습니다",
        "success",
      );
      void qc.invalidateQueries({ queryKey: QUERY_KEYS.settings });
    },
    onError: (e) => toast(extractErrorMessage(e, "설정 저장에 실패했습니다"), "error"),
  });

  return {
    dailyCapKrw: settings?.auto_rebalancing_daily_value_cap_krw ?? null,
    maxOrderValueKrw: settings?.auto_rebalancing_max_order_value_krw ?? null,
    isLoading,
    save: (value: number | null) => mutation.mutate(value),
    isSaving: mutation.isPending,
  };
}
