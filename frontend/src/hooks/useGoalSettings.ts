import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { api } from "@/api/client";
import { fetchSettings } from "@/api/settings";
import { fetchDCAAnalysis } from "@/api/invest";
import { toast } from "@/utils/toast";
import { invalidateDcaData } from "@/utils/queryInvalidation";
import { STALE_TIME } from "@/constants/queryConfig";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { useQuery } from "@tanstack/react-query";

export interface GoalForm {
  monthly_deposit_amount: string;
  goal_annual_return_pct: string;
  goal_amount: string;
  goal_start_date: string;
  goal_initial_amount: string;
  annual_deposit_goal: string;
  retirement_target_year: string;
  annual_dividend_goal: string;
}

const EMPTY_FORM: GoalForm = {
  monthly_deposit_amount: "",
  goal_annual_return_pct: "",
  goal_amount: "",
  goal_start_date: "",
  goal_initial_amount: "",
  annual_deposit_goal: "",
  retirement_target_year: "",
  annual_dividend_goal: "",
};

export function useGoalSettings() {
  const queryClient = useQueryClient();
  const location = useLocation();
  const autoOpenTriggeredRef = useRef(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.dcaAnalysis,
    queryFn: fetchDCAAnalysis,
    staleTime: STALE_TIME.EXCHANGE_RATE,
  });

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);
  const [initialForm, setInitialForm] = useState<GoalForm | null>(null);
  const [form, setForm] = useState<GoalForm>(EMPTY_FORM);

  const isDirty =
    editing && initialForm !== null ? JSON.stringify(form) !== JSON.stringify(initialForm) : false;

  const handleCloseModal = () => {
    if (isDirty) {
      setShowCloseConfirm(true);
    } else {
      setEditing(false);
    }
  };

  const openEdit = useCallback(async () => {
    const s = data?.settings;
    let annual_deposit_goal = "";
    let retirement_target_year = "";
    let annual_dividend_goal = "";
    if (data) {
      const settingsData = await fetchSettings();
      annual_deposit_goal = settingsData.annual_deposit_goal
        ? String(settingsData.annual_deposit_goal)
        : "";
      retirement_target_year = settingsData.retirement_target_year
        ? String(settingsData.retirement_target_year)
        : "";
      annual_dividend_goal = settingsData.annual_dividend_goal
        ? String(settingsData.annual_dividend_goal)
        : "";
    }
    const newForm: GoalForm = {
      monthly_deposit_amount: s?.monthly_deposit_amount ? String(s.monthly_deposit_amount) : "",
      goal_annual_return_pct: s?.goal_annual_return_pct ? String(s.goal_annual_return_pct) : "",
      goal_amount: s?.goal_amount ? String(s.goal_amount) : "",
      goal_start_date: s?.goal_start_date ?? "",
      goal_initial_amount: s?.goal_initial_amount ? String(s.goal_initial_amount) : "",
      annual_deposit_goal,
      retirement_target_year,
      annual_dividend_goal,
    };
    setForm(newForm);
    setInitialForm(newForm);
    setEditing(true);
  }, [data]);

  useEffect(() => {
    if (location.state?.openEdit && !autoOpenTriggeredRef.current && !isLoading && data) {
      autoOpenTriggeredRef.current = true;
      void openEdit();
    }
  }, [location.state, isLoading, data, openEdit]);

  useEffect(() => {
    if (!isLoading && !autoOpenTriggeredRef.current && data && !data.is_configured) {
      autoOpenTriggeredRef.current = true;
      void openEdit();
    }
  }, [isLoading, data, openEdit]);

  const saveSettings = async () => {
    setSaving(true);
    try {
      await api.put("/settings/goal", {
        monthly_deposit_amount: form.monthly_deposit_amount
          ? Number(form.monthly_deposit_amount)
          : null,
        goal_annual_return_pct: form.goal_annual_return_pct
          ? Number(form.goal_annual_return_pct)
          : null,
        goal_amount: form.goal_amount ? Number(form.goal_amount) : null,
        goal_start_date: form.goal_start_date || null,
        goal_initial_amount: form.goal_initial_amount ? Number(form.goal_initial_amount) : null,
        annual_deposit_goal: form.annual_deposit_goal ? Number(form.annual_deposit_goal) : null,
        retirement_target_year: form.retirement_target_year
          ? Number(form.retirement_target_year)
          : null,
        annual_dividend_goal: form.annual_dividend_goal
          ? Number(form.annual_dividend_goal)
          : null,
      });
      toast("설정이 저장되었습니다", "success");
      setEditing(false);
      await invalidateDcaData(queryClient);
    } catch {
      toast("저장에 실패했습니다", "error");
    } finally {
      setSaving(false);
    }
  };

  return {
    data,
    isLoading,
    isError,
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
