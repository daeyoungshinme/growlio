import { useSettingsToggle } from "@/hooks/useSettingsToggle";
import { updateMonthlyReportAlerts } from "@/api/settings";
import { invalidateMonthlyReportAlertsData } from "@/utils/queryInvalidation";

/** 매월 1일 발송되는 월간 포트폴리오 리포트 이메일 수신 on/off. */
export const useMonthlyReportAlertsToggle = () =>
  useSettingsToggle({
    field: "monthly_report_enabled",
    defaultValue: true,
    mutationFn: (enabled: boolean) => updateMonthlyReportAlerts(enabled),
    invalidate: (qc) => invalidateMonthlyReportAlertsData(qc),
  });
