import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { fetchSettings } from "@/api/settings";
import { toast } from "@/utils/toast";
import { invalidateDividendPlanData } from "@/utils/queryInvalidation";
import { useEditableSettingsForm } from "@/hooks/useEditableSettingsForm";

export interface DividendPlanForm {
  annual_dividend_goal: string;
}

const EMPTY_FORM: DividendPlanForm = {
  annual_dividend_goal: "",
};

export function useDividendPlanSettings() {
  const queryClient = useQueryClient();
  const {
    editing,
    saving,
    setSaving,
    showCloseConfirm,
    form,
    setForm,
    isDirty,
    setShowCloseConfirm,
    setEditing,
    handleCloseModal,
    startEditing,
  } = useEditableSettingsForm<DividendPlanForm>(EMPTY_FORM);

  const openEdit = async () => {
    const settingsData = await fetchSettings();
    startEditing({
      annual_dividend_goal: settingsData.annual_dividend_goal
        ? String(settingsData.annual_dividend_goal)
        : "",
    });
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      await api.put("/settings/goal", {
        annual_dividend_goal: form.annual_dividend_goal ? Number(form.annual_dividend_goal) : null,
      });
      toast("설정이 저장되었습니다", "success");
      setEditing(false);
      await invalidateDividendPlanData(queryClient);
    } catch {
      toast("저장에 실패했습니다", "error");
    } finally {
      setSaving(false);
    }
  };

  return {
    editing,
    saving,
    showCloseConfirm,
    form,
    isDirty,
    setForm,
    setShowCloseConfirm,
    setEditing,
    handleCloseModal,
    openEdit,
    saveSettings,
  };
}
