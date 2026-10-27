import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { updateCompositeSignalAlerts } from "@/api/settings";
import { invalidateCompositeSignalData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";
import { compositeSignalStatusQuery } from "@/api/queryOptions";

export function useCompositeSignalToggle() {
  const qc = useQueryClient();
  const { data: status } = useQuery(compositeSignalStatusQuery);

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
