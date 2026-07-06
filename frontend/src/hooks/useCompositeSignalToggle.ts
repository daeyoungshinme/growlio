import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCompositeSignalStatus } from "@/api/rebalancing";
import { updateCompositeSignalAlerts } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateCompositeSignalData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

export function useCompositeSignalToggle() {
  const qc = useQueryClient();
  const { data: status } = useQuery({
    queryKey: QUERY_KEYS.compositeSignalStatus,
    queryFn: fetchCompositeSignalStatus,
    staleTime: STALE_TIME.LONG,
  });

  const toggleMut = useMutation({
    mutationFn: (enabled: boolean) => updateCompositeSignalAlerts(enabled),
    onSuccess: () => {
      void invalidateCompositeSignalData(qc);
    },
    onError: (e) => toast(extractErrorMessage(e, "설정 저장에 실패했습니다"), "error"),
  });

  return {
    status,
    toggle: (enabled: boolean) => toggleMut.mutate(enabled),
    isPending: toggleMut.isPending,
  };
}
