import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import Modal from "@/components/common/Modal";
import FormInput from "@/components/common/FormInput";
import { fetchPortfolioOverviewLite, createPortfolio } from "@/api/portfolios";
import { fetchGoalFeasibility } from "@/api/invest";
import { fetchOverallGoalRecommendation } from "@/api/rebalancing";
import type { GoalRiskTolerance } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { RISK_TOLERANCE_OPTIONS } from "@/constants/goalRiskTolerance";
import { fmtKrw, fmtKrwPreview, fmtPct } from "@/utils/format";
import { classifyGoalFeasibility } from "@/utils/goalFeasibility";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { invalidatePortfolioData } from "@/utils/queryInvalidation";
import type { GoalForm } from "@/hooks/useGoalSettings";

const STEP_TITLES = [
  "현재 자산 확인",
  "목표 금액과 시점",
  "월 적립액",
  "결과 확인",
  "투자성향·배당목표",
  "추천 포트폴리오",
];
const TOTAL_STEPS = STEP_TITLES.length;
const RECOMMENDATION_STEP = 6;

// 백엔드 DEPOSIT_GUIDE_PRESET_RETURNS_PCT(4/7/10%)와 배열 순서로 매칭되는 표시용 레이블
const DEPOSIT_GUIDE_PRESET_LABELS = ["보수적", "중립", "공격적"];

interface Props {
  form: GoalForm;
  setForm: Dispatch<SetStateAction<GoalForm>>;
  step: number;
  setStep: Dispatch<SetStateAction<number>>;
  saving: boolean;
  onSave: () => void;
  onClose: () => void;
}

/** 목표를 처음 설정하는 사용자를 위한 6단계 가이드 — 필요 연수익률과 필요 적립액을 스스로
 * 지어내지 않도록 `/invest/goal-feasibility`로 역산해 보여준다. 3단계(월 적립액)는 가정
 * 수익률 프리셋별 필요 월/연 적립액을, 4단계(결과 확인)는 입력한 적립액 기준 필요 연수익률을
 * 계산해 각각 기본값으로 제안한다. 5단계(투자성향·배당목표)는 출생연도·리스크 성향·배당목표를
 * 추가로 받아 6단계 진입 시 자동 저장(`onSave`)한 뒤 `/rebalancing/goal-recommendation`(전체
 * 자산 기준 목표 역산 추천)을 조회해 보여주고, "이 추천으로 포트폴리오 만들기"를 누르면 그
 * 비중 그대로 신규 Portfolio를 생성한다(계좌 연결 없는 가상 목표비중 — `RecommendationCard`의
 * "새 포트폴리오 만들기"와 동일한 개념). 기존 플랫 편집 모달(InvestPlanPage.tsx)은 재설정용으로
 * 별도 유지되며 이 컴포넌트를 대체하지 않는다. */
export default function GoalSettingWizard({
  form,
  setForm,
  step,
  setStep,
  saving,
  onSave,
  onClose,
}: Props) {
  const { data: overview } = useQuery({
    queryKey: QUERY_KEYS.portfolioOverviewLite,
    queryFn: fetchPortfolioOverviewLite,
    staleTime: STALE_TIME.MEDIUM,
  });
  // 부동산은 목표 역산 추천/DCA 복리 곡선이 성장을 모델링하지 않으므로 투자자산
  // 초기값에서 제외 — 목표 진행율 추적 기준(dca_service.py)과 일치시킨다.
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

  const canProceed = step !== 2 || (goalAmountNum > 0 && targetYearNum > 0);
  const band = feasibility ? classifyGoalFeasibility(feasibility.required_return_pct) : null;

  // 6단계(추천 포트폴리오) 진입 시 1회 자동 저장 — 재진입(이전→다음) 시 값이 바뀌었을 수 있으므로
  // step이 6에서 벗어났다가 다시 들어올 때마다 다시 트리거한다. onSave(=saveSettings)는
  // 매 렌더 새 함수 참조라 effect deps에 직접 넣으면 무한 재실행되므로 ref로 최신값만 참조한다.
  const onSaveRef = useRef(onSave);
  useEffect(() => {
    onSaveRef.current = onSave;
  }, [onSave]);
  const enteredRecommendationStepRef = useRef(false);
  const [settingsPersisted, setSettingsPersisted] = useState(false);
  const prevSavingRef = useRef(saving);

  useEffect(() => {
    if (step === RECOMMENDATION_STEP && !enteredRecommendationStepRef.current) {
      enteredRecommendationStepRef.current = true;
      setSettingsPersisted(false);
      onSaveRef.current();
    } else if (step !== RECOMMENDATION_STEP) {
      enteredRecommendationStepRef.current = false;
    }
  }, [step]);

  useEffect(() => {
    if (prevSavingRef.current && !saving && enteredRecommendationStepRef.current) {
      setSettingsPersisted(true);
    }
    prevSavingRef.current = saving;
  }, [saving]);

  const queryClient = useQueryClient();
  const { data: recommendation, isLoading: recommendationLoading } = useQuery({
    queryKey: QUERY_KEYS.goalRecommendationOverall,
    queryFn: fetchOverallGoalRecommendation,
    enabled: step === RECOMMENDATION_STEP && settingsPersisted,
    staleTime: 0,
  });

  const createPortfolioMutation = useMutation({
    mutationFn: () =>
      createPortfolio({
        name: "추천 포트폴리오",
        items: (recommendation?.recommended_items ?? []).map((item) => ({
          ticker: item.ticker,
          name: item.name,
          market: item.market,
          weight: item.weight,
        })),
      }),
    onSuccess: async () => {
      toast("추천 포트폴리오가 생성되었습니다", "success");
      await invalidatePortfolioData(queryClient);
      onClose();
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  return (
    <Modal title={`목표 설정 가이드 (${step}/${TOTAL_STEPS})`} onClose={onClose} size="md">
      <div className="overflow-y-auto overscroll-contain px-6 pb-6 pt-2 space-y-4 flex-1">
        <div className="flex items-center gap-1.5">
          {STEP_TITLES.map((title, i) => (
            <div
              key={title}
              className={`h-1.5 flex-1 rounded-full ${
                i + 1 <= step ? "bg-blue-600" : "bg-gray-200 dark:bg-gray-700"
              }`}
            />
          ))}
        </div>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          {STEP_TITLES[step - 1]}
        </h3>

        {step === 1 && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              목표 계산의 시작점이 되는 현재 자산입니다. 비워두면 최근 자산 스냅샷이 자동으로
              사용됩니다.
            </p>
            <FormInput
              label="투자 시작시점 자산 (원)"
              type="number"
              inputMode="numeric"
              value={form.goal_initial_amount}
              onChange={(e) => setForm((f) => ({ ...f, goal_initial_amount: e.target.value }))}
              placeholder={currentAssets != null ? String(Math.round(currentAssets)) : "100000000"}
              preview={
                form.goal_initial_amount
                  ? fmtKrwPreview(Number(form.goal_initial_amount))
                  : undefined
              }
              hint={
                currentAssets != null
                  ? `현재 투자자산(부동산 제외) 약 ${fmtKrw(currentAssets)} — 비워두면 이 값이 자동 사용됩니다`
                  : "비워두면 스냅샷 자동 사용"
              }
            />
            {currentAssets != null && (
              <button
                type="button"
                onClick={() =>
                  setForm((f) => ({ ...f, goal_initial_amount: String(Math.round(currentAssets)) }))
                }
                className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
              >
                현재 자산 값으로 채우기
              </button>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              은퇴자금, 주택자금 등 최종적으로 모으고 싶은 금액과 그 시점을 입력하세요.
            </p>
            <FormInput
              label="목표 금액 (원)"
              type="number"
              inputMode="numeric"
              required
              value={form.goal_amount}
              onChange={(e) => setForm((f) => ({ ...f, goal_amount: e.target.value }))}
              placeholder="500000000"
              preview={form.goal_amount ? fmtKrwPreview(Number(form.goal_amount)) : undefined}
            />
            <FormInput
              label="목표 시점 (연도)"
              type="number"
              inputMode="numeric"
              required
              value={form.retirement_target_year}
              onChange={(e) => setForm((f) => ({ ...f, retirement_target_year: e.target.value }))}
              placeholder="2045"
              hint="대시보드 투자 목표 카드에도 함께 표시됩니다"
            />
          </div>
        )}

        {step === 3 && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              매달 얼마씩 적립할 계획인가요? 연간 입금 목표는 자동으로 계산되며 직접 조정할 수
              있습니다.
            </p>
            <FormInput
              label="월 적립액 (원)"
              type="number"
              inputMode="numeric"
              value={form.monthly_deposit_amount}
              onChange={(e) => {
                const v = e.target.value;
                setForm((f) => ({
                  ...f,
                  monthly_deposit_amount: v,
                  annual_deposit_goal:
                    f.annual_deposit_goal || (v ? String(Number(v) * 12) : f.annual_deposit_goal),
                }));
              }}
              placeholder="500000"
              preview={
                form.monthly_deposit_amount
                  ? fmtKrwPreview(Number(form.monthly_deposit_amount))
                  : undefined
              }
            />
            <FormInput
              label="연간 입금 목표 (원)"
              type="number"
              inputMode="numeric"
              value={form.annual_deposit_goal}
              onChange={(e) => setForm((f) => ({ ...f, annual_deposit_goal: e.target.value }))}
              placeholder="6000000"
              preview={
                form.annual_deposit_goal
                  ? fmtKrwPreview(Number(form.annual_deposit_goal))
                  : undefined
              }
              hint="월 적립액 × 12로 자동 계산 — 대시보드 입금 달성률에 표시, 직접 조정 가능"
            />

            <div className="pt-1 space-y-2">
              <p className="text-xs text-gray-500 dark:text-gray-400">
                얼마를 적립해야 할지 감이 안 온다면, 가정 수익률별 필요 적립액을 참고해 바로
                채워보세요.
              </p>
              {feasibilityLoading && (
                <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
                  <Loader2 size={14} className="animate-spin" /> 계산하고 있어요...
                </div>
              )}
              {feasibility?.deposit_guide.map((item, i) => (
                <div
                  key={item.annual_return_pct}
                  className="flex items-center justify-between gap-2 p-2.5 rounded-lg bg-gray-50 dark:bg-gray-800"
                >
                  <div>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {DEPOSIT_GUIDE_PRESET_LABELS[i] ?? "가정"} (연 {item.annual_return_pct}%)
                    </p>
                    <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                      월 {fmtKrw(item.required_monthly_deposit)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      setForm((f) => ({
                        ...f,
                        monthly_deposit_amount: String(Math.round(item.required_monthly_deposit)),
                        annual_deposit_goal: String(Math.round(item.required_annual_deposit)),
                      }))
                    }
                    className="shrink-0 text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    이 값으로 채우기
                  </button>
                </div>
              ))}
              {feasibility?.deposit_guide.length === 0 && feasibility.note && (
                <p className="text-xs text-gray-400 dark:text-gray-500">{feasibility.note}</p>
              )}
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-3">
            {feasibilityLoading && (
              <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
                <Loader2 size={14} className="animate-spin" /> 필요 수익률을 계산하고 있어요...
              </div>
            )}
            {feasibility && (
              <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800 space-y-2">
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  목표 달성에 필요한 연평균 수익률
                </p>
                <p className="text-2xl font-bold text-gray-900 dark:text-gray-50">
                  {feasibility.required_return_pct != null
                    ? fmtPct(feasibility.required_return_pct)
                    : "—"}
                </p>
                {band && (
                  <span
                    className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${band.cls}`}
                  >
                    {band.label}
                  </span>
                )}
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {feasibility.note ?? band?.description}
                </p>
              </div>
            )}
            <FormInput
              label="목표 연수익률 (%)"
              type="number"
              inputMode="decimal"
              value={form.goal_annual_return_pct}
              onChange={(e) => setForm((f) => ({ ...f, goal_annual_return_pct: e.target.value }))}
              placeholder="8"
              hint="계산된 필요 수익률이 기본값으로 채워집니다 — 직접 조정 가능"
            />
            <Link
              to="/rebalancing?rtab=포트폴리오"
              className="block text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
            >
              추천 포트폴리오 보러가기 →
            </Link>
          </div>
        )}

        {step === 5 && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              이 정보를 바탕으로 다음 단계에서 맞춤 포트폴리오를 추천해드려요. 모두 선택 입력이라
              건너뛰어도 괜찮아요.
            </p>
            <FormInput
              label="출생연도"
              type="number"
              inputMode="numeric"
              value={form.birth_year}
              onChange={(e) => setForm((f) => ({ ...f, birth_year: e.target.value }))}
              placeholder="1990"
              hint="연령대에 맞는 주식비중 상/하한을 함께 고려합니다"
            />
            <div>
              <label
                htmlFor="goal-wizard-risk-tolerance"
                className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
              >
                투자성향
              </label>
              <select
                id="goal-wizard-risk-tolerance"
                value={form.goal_risk_tolerance}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    goal_risk_tolerance: e.target.value as GoalRiskTolerance,
                  }))
                }
                className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {RISK_TOLERANCE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <p className="text-xs text-gray-400 mt-1">
                목표 달성에 필요한 최소 수익률보다 더 높은 수익률을 목표로 삼을수록 변동성도
                커집니다.
              </p>
            </div>
            <FormInput
              label="연간 배당목표 (원)"
              type="number"
              inputMode="numeric"
              value={form.annual_dividend_goal}
              onChange={(e) => setForm((f) => ({ ...f, annual_dividend_goal: e.target.value }))}
              placeholder="3000000"
              preview={
                form.annual_dividend_goal
                  ? fmtKrwPreview(Number(form.annual_dividend_goal))
                  : undefined
              }
              hint="설정하면 추천 포트폴리오가 배당수익률도 함께 고려합니다"
            />
          </div>
        )}

        {step === RECOMMENDATION_STEP && (
          <div className="space-y-3">
            {(!settingsPersisted || recommendationLoading) && (
              <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
                <Loader2 size={14} className="animate-spin" /> 추천 포트폴리오를 계산하고 있어요...
              </div>
            )}
            {settingsPersisted && recommendation && recommendation.recommended_items.length > 0 && (
              <div className="space-y-2">
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-2.5 rounded-lg bg-gray-50 dark:bg-gray-800">
                    <p className="text-xs text-gray-500 dark:text-gray-400">기대수익률</p>
                    <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                      {recommendation.expected_return_pct != null
                        ? fmtPct(recommendation.expected_return_pct)
                        : "—"}
                    </p>
                  </div>
                  <div className="p-2.5 rounded-lg bg-gray-50 dark:bg-gray-800">
                    <p className="text-xs text-gray-500 dark:text-gray-400">예상 변동성</p>
                    <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                      {recommendation.expected_volatility_pct != null
                        ? fmtPct(recommendation.expected_volatility_pct)
                        : "—"}
                    </p>
                  </div>
                </div>
                <div className="space-y-1.5">
                  {recommendation.recommended_items.map((item) => (
                    <div
                      key={`${item.ticker}-${item.market}`}
                      className="flex items-center justify-between text-xs p-2 rounded-lg bg-gray-50 dark:bg-gray-800"
                    >
                      <span className="text-gray-700 dark:text-gray-300">
                        {item.name || item.ticker}
                      </span>
                      <span className="font-semibold text-gray-900 dark:text-gray-50">
                        {item.weight.toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
                {recommendation.note && (
                  <p className="text-xs text-gray-400 dark:text-gray-500">{recommendation.note}</p>
                )}
                <button
                  type="button"
                  onClick={() => createPortfolioMutation.mutate()}
                  disabled={createPortfolioMutation.isPending}
                  className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} w-full flex items-center justify-center gap-1.5 px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors`}
                >
                  {createPortfolioMutation.isPending && (
                    <Loader2 size={14} className="animate-spin" />
                  )}
                  이 추천으로 포트폴리오 만들기
                </button>
              </div>
            )}
            {settingsPersisted &&
              recommendation &&
              recommendation.recommended_items.length === 0 && (
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {recommendation.note ??
                    "추천을 계산하지 못했습니다 — 나중에 리밸런싱 탭에서 다시 시도해보세요"}
                </p>
              )}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          {step > 1 && (
            <button
              type="button"
              onClick={() => setStep((s) => s - 1)}
              className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors`}
            >
              이전
            </button>
          )}
          {step < TOTAL_STEPS ? (
            <button
              type="button"
              disabled={!canProceed}
              onClick={() => setStep((s) => s + 1)}
              className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors`}
            >
              {/* 5단계(마지막 입력 단계)의 "다음"이 실제 저장 트리거 — 6단계 진입 시 자동 저장된다 */}
              다음
            </button>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors`}
            >
              완료
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
