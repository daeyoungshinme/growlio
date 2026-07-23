import { useSettingsToggle } from "@/hooks/useSettingsToggle";
import { updateYearEndTaxReminder } from "@/api/settings";
import { invalidateYearEndTaxReminderData } from "@/utils/queryInvalidation";

/** 11~12월 매주 월요일 09:00 KST 연말 절세 리마인더 on/off. */
export const useYearEndTaxReminderToggle = () =>
  useSettingsToggle({
    field: "year_end_tax_reminder_enabled",
    defaultValue: false,
    mutationFn: (enabled: boolean) => updateYearEndTaxReminder(enabled),
    invalidate: (qc) => invalidateYearEndTaxReminderData(qc),
  });
