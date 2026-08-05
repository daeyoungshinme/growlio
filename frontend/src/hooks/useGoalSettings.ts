import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { api } from "@/api/client";
import { fetchSettings, type GoalRiskTolerance } from "@/api/settings";
import { fetchDCAAnalysis } from "@/api/invest";
import { toast } from "@/utils/toast";
import { invalidateDcaData, invalidateGoalRecommendationData } from "@/utils/queryInvalidation";
import { STALE_TIME } from "@/constants/queryConfig";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { useQuery } from "@tanstack/react-query";
import { useEditableSettingsForm } from "@/hooks/useEditableSettingsForm";

export interface GoalForm {
  monthly_deposit_amount: string;
  goal_annual_return_pct: string;
  goal_amount: string;
  goal_start_date: string;
  goal_initial_amount: string;
  annual_deposit_goal: string;
  retirement_target_year: string;
  /** 온보딩 전용(마법사 5단계) — 출생연도. 저장 시 서버가 age_group을 자동 파생한다. */
  birth_year: string;
  /** 온보딩 전용(마법사 5단계) — 연간 배당목표. 배당 계획 탭(`useDividendPlanSettings`)과 같은
   * `UserSettings.annual_dividend_goal` 필드를 공유한다. */
  annual_dividend_goal: string;
  /** 온보딩 전용(마법사 5단계) — 목표 역산 추천 리스크 성향. 마법사에서만 저장을 트리거한다
   * (플랫 편집 모달에는 UI가 없어 기존 값을 그대로 되돌려 보낸다). */
  goal_risk_tolerance: GoalRiskTolerance;
}

const EMPTY_FORM: GoalForm = {
  monthly_deposit_amount: "",
  goal_annual_return_pct: "",
  goal_amount: "",
  goal_start_date: "",
  goal_initial_amount: "",
  annual_deposit_goal: "",
  retirement_target_year: "",
  birth_year: "",
  annual_dividend_goal: "",
  goal_risk_tolerance: "CONSERVATIVE",
};

export function useGoalSettings() {
  const queryClient = useQueryClient();
  const location = useLocation();
  const autoOpenTriggeredRef = useRef(false);
  const [wizardMode, setWizardMode] = useState(false);
  const [wizardStep, setWizardStep] = useState(1);

  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.dcaAnalysis,
    queryFn: fetchDCAAnalysis,
    staleTime: STALE_TIME.EXCHANGE_RATE,
  });

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
  } = useEditableSettingsForm<GoalForm>(EMPTY_FORM);

  const buildCurrentForm = useCallback(async (): Promise<GoalForm> => {
    const s = data?.settings;
    let annual_deposit_goal = "";
    let retirement_target_year = "";
    let birth_year = "";
    let annual_dividend_goal = "";
    let goal_risk_tolerance: GoalRiskTolerance = "CONSERVATIVE";
    if (data) {
      const settingsData = await fetchSettings();
      annual_deposit_goal = settingsData.annual_deposit_goal
        ? String(settingsData.annual_deposit_goal)
        : "";
      retirement_target_year = settingsData.retirement_target_year
        ? String(settingsData.retirement_target_year)
        : "";
      birth_year = settingsData.birth_year ? String(settingsData.birth_year) : "";
      annual_dividend_goal = settingsData.annual_dividend_goal
        ? String(settingsData.annual_dividend_goal)
        : "";
      goal_risk_tolerance = settingsData.goal_risk_tolerance ?? "CONSERVATIVE";
    }
    return {
      monthly_deposit_amount: s?.monthly_deposit_amount ? String(s.monthly_deposit_amount) : "",
      goal_annual_return_pct: s?.goal_annual_return_pct ? String(s.goal_annual_return_pct) : "",
      goal_amount: s?.goal_amount ? String(s.goal_amount) : "",
      goal_start_date: s?.goal_start_date ?? "",
      goal_initial_amount: s?.goal_initial_amount ? String(s.goal_initial_amount) : "",
      annual_deposit_goal,
      retirement_target_year,
      birth_year,
      annual_dividend_goal,
      goal_risk_tolerance,
    };
  }, [data]);

  const openEdit = useCallback(async () => {
    setWizardMode(false);
    startEditing(await buildCurrentForm());
  }, [buildCurrentForm, startEditing]);

  const openWizard = useCallback(async () => {
    setWizardMode(true);
    setWizardStep(1);
    startEditing(await buildCurrentForm());
  }, [buildCurrentForm, startEditing]);

  useEffect(() => {
    if (location.state?.openEdit && !autoOpenTriggeredRef.current && !isLoading && data) {
      autoOpenTriggeredRef.current = true;
      void openEdit();
    }
  }, [location.state, isLoading, data, openEdit]);

  useEffect(() => {
    const alreadyShown = localStorage.getItem("growlio:goal-wizard-auto-shown") === "true";
    if (
      !isLoading &&
      !autoOpenTriggeredRef.current &&
      data &&
      !data.is_configured &&
      !alreadyShown
    ) {
      autoOpenTriggeredRef.current = true;
      localStorage.setItem("growlio:goal-wizard-auto-shown", "true");
      void openWizard();
    }
  }, [isLoading, data, openWizard]);

  /** wizardMode에서는 5단계(투자성향·배당목표) 저장 후 6단계(추천 포트폴리오)로 넘어가므로
   * 모달을 닫지 않는다 — 플랫 편집 모달(!wizardMode)만 저장 즉시 닫힌다. */
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
        goal_start_date:
          form.goal_start_date || (wizardMode ? new Date().toISOString().slice(0, 10) : null),
        goal_initial_amount: form.goal_initial_amount ? Number(form.goal_initial_amount) : null,
        annual_deposit_goal: form.annual_deposit_goal ? Number(form.annual_deposit_goal) : null,
        retirement_target_year: form.retirement_target_year
          ? Number(form.retirement_target_year)
          : null,
        annual_dividend_goal: form.annual_dividend_goal ? Number(form.annual_dividend_goal) : null,
        birth_year: form.birth_year ? Number(form.birth_year) : null,
      });
      if (wizardMode) {
        // 리스크 성향은 전체교체 엔드포인트라 다른 필드(종목당 최대비중 등)를 덮어쓰지 않도록
        // 저장 직전 최신값을 조회해 리스크 성향만 갈아끼워 되돌려 보낸다.
        const current = await fetchSettings();
        await api.put("/settings/goal-recommendation-options", {
          risk_tolerance: form.goal_risk_tolerance,
          max_weight_pct: current.goal_max_weight_pct,
          cagr_lookback_years: current.goal_cagr_lookback_years,
          short_term_equity_floor_pct: current.goal_short_term_equity_floor_pct,
          age_group: current.age_group,
          bond_ceiling_pct: current.goal_bond_ceiling_pct,
          cash_ceiling_pct: current.goal_cash_ceiling_pct,
        });
        await invalidateGoalRecommendationData(queryClient);
      }
      toast("설정이 저장되었습니다", "success");
      if (!wizardMode) setEditing(false);
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
    wizardMode,
    wizardStep,
    setWizardStep,
    openWizard,
  };
}
