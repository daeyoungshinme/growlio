import { useEffect, type Dispatch, type SetStateAction } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchPortfolioOverviewLite } from "@/api/portfolios";
import { fetchGoalFeasibility } from "@/api/invest";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { classifyGoalFeasibility } from "@/utils/goalFeasibility";
import type { GoalForm } from "@/hooks/useGoalSettings";

/** 위저드 1~4단계가 쓰는 현재 자산·목표 실현 가능성 조회. 4단계 진입 시 필요 수익률을 목표 연수익률로 1회 prefill한다. */
export function useGoalWizardFeasibility(
  form: GoalForm,
  setForm: Dispatch<SetStateAction<GoalForm>>,
  step: number,
) {
  const { data: overview } = useQuery({
    queryKey: QUERY_KEYS.portfolioOverviewLite,
    queryFn: fetchPortfolioOverviewLite,
    staleTime: STALE_TIME.MEDIUM,
  });
  // 부동산은 목표 역산 추천/DCA 복리 곡선이 성장을 모델링하지 않으므로 투자자산
  // 초기값에서 제외 — 목표 진행률 추적 기준(dca_service.py)과 일치시킨다.
  const realEstateKrw =
    overview?.asset_type_allocation?.find((a) => a.type === "REAL_ESTATE")?.amount_krw ?? 0;
  const currentAssets = overview ? overview.total_assets_krw - realEstateKrw : null;

  const goalAmountNum = form.goal_amount ? Number(form.goal_amount) : 0;
  const targetYearNum = form.retirement_target_year ? Number(form.retirement_target_year) : 0;
  const monthlyNum = form.monthly_deposit_amount ? Number(form.monthly_deposit_amount) : 0;
  // 3단계(월 적립액 가이드)는 monthly_deposit_amount와 무관한 deposit_guide만 사용하므로,
  // 타이핑할 때마다 재조회되지 않도록 쿼리키에서는 이 단계의 적립액 입력을 무시한다.
  const monthlyForQuery = step === 4 ? monthlyNum : 0;
  const hasCustomInitial = form.goal_initial_amount !== "";
  const initialAmountNum = hasCustomInitial
    ? Number(form.goal_initial_amount)
    : (currentAssets ?? 0);

  const feasibilityEnabled =
    (step === 3 || step === 4) &&
    goalAmountNum > 0 &&
    targetYearNum > 0 &&
    (hasCustomInitial || currentAssets != null);

  const { data: feasibility, isLoading: feasibilityLoading } = useQuery({
    queryKey: QUERY_KEYS.goalFeasibility(
      goalAmountNum,
      targetYearNum,
      monthlyForQuery,
      initialAmountNum,
    ),
    queryFn: () =>
      fetchGoalFeasibility({
        goal_amount: goalAmountNum,
        target_year: targetYearNum,
        monthly_deposit_amount: monthlyForQuery,
        initial_amount: initialAmountNum,
      }),
    enabled: feasibilityEnabled,
    staleTime: STALE_TIME.SHORT,
  });

  useEffect(() => {
    if (feasibility?.required_return_pct != null && !form.goal_annual_return_pct) {
      const suggested = feasibility.required_return_pct;
      setForm((f) =>
        f.goal_annual_return_pct ? f : { ...f, goal_annual_return_pct: String(suggested) },
      );
    }
    // form.goal_annual_return_pct는 의도적으로 제외 — 최초 1회만 prefill하고 이후 사용자 입력을 덮어쓰지 않음
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feasibility, setForm]);

  return {
    currentAssets,
    feasibility,
    feasibilityLoading,
    band: feasibility ? classifyGoalFeasibility(feasibility.required_return_pct) : null,
    // 2단계(목표 금액·시점)는 두 값이 모두 있어야 다음으로 넘어갈 수 있다
    canProceed: step !== 2 || (goalAmountNum > 0 && targetYearNum > 0),
  };
}
