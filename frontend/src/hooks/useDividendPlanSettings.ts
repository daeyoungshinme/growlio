import { useQueryClient } from "@tanstack/react-query";
import { fetchSettings, updateGoalSettings } from "@/api/settings";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { invalidateDcaData, invalidateGoalRecommendationData } from "@/utils/queryInvalidation";
import { numberFieldPayload, useEditableSettingsForm } from "@/hooks/useEditableSettingsForm";

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
    initialForm,
    isDirty,
    setShowCloseConfirm,
    setEditing,
    handleCloseModal,
    startEditing,
  } = useEditableSettingsForm<DividendPlanForm>(EMPTY_FORM);

  const openEdit = async () => {
    let settingsData: Awaited<ReturnType<typeof fetchSettings>>;
    try {
      settingsData = await fetchSettings();
    } catch (e) {
      // onClick에 직접 묶인 async라 실패하면 탭이 아무 반응 없이 끝나고 rejection이 처리되지 않았다
      toast(extractErrorMessage(e), "error");
      return;
    }
    startEditing({
      annual_dividend_goal: settingsData.annual_dividend_goal
        ? String(settingsData.annual_dividend_goal)
        : "",
    });
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      await updateGoalSettings({
        annual_dividend_goal: numberFieldPayload(
          form.annual_dividend_goal,
          initialForm?.annual_dividend_goal,
        ),
      });
      toast("설정이 저장되었습니다", "success");
      setEditing(false);
      // PUT /settings/goal은 대시보드·DCA·챌린지·목표 추천 캐시를 함께 지운다 — 배당 계획만
      // 무효화하면 홈 목표 카드와 설정의 "목표 N개"가 오래된 배당 목표를 보인다.
      await Promise.all([
        invalidateDcaData(queryClient),
        invalidateGoalRecommendationData(queryClient),
      ]);
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
