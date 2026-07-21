import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchSettings, updateMonthlyReportAlerts } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateMonthlyReportAlertsData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

/** 매월 1일 발송되는 월간 포트폴리오 리포트 이메일 수신 on/off. */
export function useMonthlyReportAlertsToggle() {
  const qc = useQueryClient();
  const { data: settings } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });

  const toggleMut = useMutation({
    mutationFn: (enabled: boolean) => updateMonthlyReportAlerts(enabled),
    onSuccess: () => {
      void invalidateMonthlyReportAlertsData(qc);
    },
    onError: (e) => toast(extractErrorMessage(e, "설정 저장에 실패했습니다"), "error"),
  });

  return {
    enabled: settings?.monthly_report_enabled ?? true,
    toggle: (enabled: boolean) => toggleMut.mutate(enabled),
    isPending: toggleMut.isPending,
  };
}
