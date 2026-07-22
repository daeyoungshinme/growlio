import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchSettings, updateYearEndTaxReminder } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateYearEndTaxReminderData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

/** 11~12월 매주 월요일 09:00 KST 연말 절세 리마인더 on/off. */
export function useYearEndTaxReminderToggle() {
  const qc = useQueryClient();
  const { data: settings } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });

  const toggleMut = useMutation({
    mutationFn: (enabled: boolean) => updateYearEndTaxReminder(enabled),
    onSuccess: () => {
      void invalidateYearEndTaxReminderData(qc);
    },
    onError: (e) => toast(extractErrorMessage(e, "설정 저장에 실패했습니다"), "error"),
  });

  return {
    enabled: settings?.year_end_tax_reminder_enabled ?? false,
    toggle: (enabled: boolean) => toggleMut.mutate(enabled),
    isPending: toggleMut.isPending,
  };
}
