import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import {
  fetchSettings,
  updateGoalRecommendationOptions,
  updateGoalSettings,
  type GoalRiskTolerance,
} from "@/api/settings";
import { dcaAnalysisQuery } from "@/api/queryOptions";
import { toast } from "@/utils/toast";
import { localToday } from "@/utils/format";
import { invalidateDcaData } from "@/utils/queryInvalidation";
import { useQuery } from "@tanstack/react-query";
import { numberFieldPayload, useEditableSettingsForm } from "@/hooks/useEditableSettingsForm";
import { storageGet, storageSet } from "@/utils/safeStorage";

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

  const { data, isLoading, isError } = useQuery(dcaAnalysisQuery);

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

  // buildCurrentForm은 설정을 다시 조회하므로 실패할 수 있다 — 호출부가 `void`로 부르므로
  // 여기서 잡지 않으면 unhandled rejection이 되고 모달이 아무 안내 없이 열리지 않는다.
  const openEdit = useCallback(async () => {
    setWizardMode(false);
    try {
      startEditing(await buildCurrentForm());
    } catch {
      toast("설정을 불러오지 못했습니다", "error");
    }
  }, [buildCurrentForm, startEditing]);

  const openWizard = useCallback(async () => {
    setWizardMode(true);
    setWizardStep(1);
    try {
      startEditing(await buildCurrentForm());
    } catch {
      toast("설정을 불러오지 못했습니다", "error");
    }
  }, [buildCurrentForm, startEditing]);

  useEffect(() => {
    if (location.state?.openEdit && !autoOpenTriggeredRef.current && !isLoading && data) {
      autoOpenTriggeredRef.current = true;
      void openEdit();
    }
  }, [location.state, isLoading, data, openEdit]);

  useEffect(() => {
    const alreadyShown = storageGet("growlio:goal-wizard-auto-shown") === "true";
    if (
      !isLoading &&
      !autoOpenTriggeredRef.current &&
      data &&
      !data.is_configured &&
      !alreadyShown
    ) {
      autoOpenTriggeredRef.current = true;
      storageSet("growlio:goal-wizard-auto-shown", "true");
      void openWizard();
    }
  }, [isLoading, data, openWizard]);

  /** wizardMode에서는 5단계(투자성향·배당목표) 저장 후 6단계(추천 포트폴리오)로 넘어가므로
   * 모달을 닫지 않는다 — 플랫 편집 모달(!wizardMode)만 저장 즉시 닫힌다.
   * 성공 여부를 돌려준다 — 마법사 6단계가 실패 시 이전 설정 기준 추천을 보여주지 않도록. */
  const saveSettings = async (): Promise<boolean> => {
    setSaving(true);
    try {
      // 비운 필드는 null(백엔드가 지움), 처음부터 비어 있던 필드는 생략(기존 값 유지)
      const init = initialForm ?? undefined;
      await updateGoalSettings({
        monthly_deposit_amount: numberFieldPayload(
          form.monthly_deposit_amount,
          init?.monthly_deposit_amount,
        ),
        goal_annual_return_pct: numberFieldPayload(
          form.goal_annual_return_pct,
          init?.goal_annual_return_pct,
        ),
        goal_amount: numberFieldPayload(form.goal_amount, init?.goal_amount),
        // 플랫 편집 모달에서도 비워두면 오늘 날짜로 기본값 처리 — wizardMode에서만 기본값을
        // 적용하면 마법사를 거치지 않고 플랫 모달로만 목표를 편집한 사용자는 goal_start_date가
        // null로 저장되어 dca_service의 is_configured가 계속 false로 남고(목표 진행률 카드가
        // "미설정"으로 보임), 목표 설정 가이드 모달이 브라우저를 바꿀 때마다 다시 뜬다.
        goal_start_date: form.goal_start_date || localToday(),
        goal_initial_amount: numberFieldPayload(
          form.goal_initial_amount,
          init?.goal_initial_amount,
        ),
        annual_deposit_goal: numberFieldPayload(
          form.annual_deposit_goal,
          init?.annual_deposit_goal,
        ),
        retirement_target_year: numberFieldPayload(
          form.retirement_target_year,
          init?.retirement_target_year,
        ),
        annual_dividend_goal: numberFieldPayload(
          form.annual_dividend_goal,
          init?.annual_dividend_goal,
        ),
        birth_year: numberFieldPayload(form.birth_year, init?.birth_year),
      });
      if (wizardMode) {
        // 리스크 성향은 전체교체 엔드포인트라 다른 필드(종목당 최대비중 등)를 덮어쓰지 않도록
        // 저장 직전 최신값을 조회해 리스크 성향만 갈아끼워 되돌려 보낸다.
        const current = await fetchSettings();
        await updateGoalRecommendationOptions({
          risk_tolerance: form.goal_risk_tolerance,
          max_weight_pct: current.goal_max_weight_pct,
          cagr_lookback_years: current.goal_cagr_lookback_years,
          short_term_equity_floor_pct: current.goal_short_term_equity_floor_pct,
          age_group: current.age_group,
          bond_ceiling_pct: current.goal_bond_ceiling_pct,
          cash_ceiling_pct: current.goal_cash_ceiling_pct,
        });
      }
      // 목표 금액·연도·출생연도는 마법사 밖(편집 모달)에서도 바뀌고 추천 결과를 바꾼다 — 백엔드도
      // 저장 시 추천 캐시를 지우므로 프론트도 모드와 무관하게 무효화한다(persist 대상 키).
      const dcaInvalidation = invalidateDcaData(queryClient, { goalRecommendation: true });
      toast("설정이 저장되었습니다", "success");
      if (!wizardMode) setEditing(false);
      await dcaInvalidation;
      return true;
    } catch {
      toast("저장에 실패했습니다", "error");
      return false;
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
