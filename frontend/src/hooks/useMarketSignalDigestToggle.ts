import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchSettings, updateMarketSignalDigest } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateMarketSignalDigestData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

/** 매일 08:30 KST 시장신호 요약 알림 on/off — 등급 전환 시 즉시 알림(useCompositeSignalToggle)과 별개 설정. */
export function useMarketSignalDigestToggle() {
  const qc = useQueryClient();
  const { data: settings } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });

  const toggleMut = useMutation({
    mutationFn: (enabled: boolean) => updateMarketSignalDigest(enabled),
    onSuccess: () => {
      void invalidateMarketSignalDigestData(qc);
    },
    onError: (e) => toast(extractErrorMessage(e, "설정 저장에 실패했습니다"), "error"),
  });

  return {
    enabled: settings?.market_signal_daily_digest_enabled ?? false,
    toggle: (enabled: boolean) => toggleMut.mutate(enabled),
    isPending: toggleMut.isPending,
  };
}
