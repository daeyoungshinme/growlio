import type { Dispatch, SetStateAction } from "react";
import Modal from "@/components/common/Modal";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import type { GoalForm } from "@/hooks/useGoalSettings";
import {
  GoalTargetStep,
  InitialAssetsStep,
  InvestorProfileStep,
} from "./goalWizard/GoalWizardInputSteps";
import { MonthlyDepositStep, RequiredReturnStep } from "./goalWizard/GoalWizardFeasibilitySteps";
import GoalWizardRecommendationStep from "./goalWizard/GoalWizardRecommendationStep";
import { useGoalWizardFeasibility } from "./goalWizard/useGoalWizardFeasibility";
import {
  RECOMMENDATION_STEP,
  useRecommendationStepAutosave,
} from "./goalWizard/useRecommendationStepAutosave";

const STEP_TITLES = [
  "현재 자산 확인",
  "목표 금액과 시점",
  "월 적립액",
  "결과 확인",
  "투자성향·배당목표",
  "추천 포트폴리오",
];
const TOTAL_STEPS = STEP_TITLES.length;

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
  const { currentAssets, feasibility, feasibilityLoading, band, canProceed } =
    useGoalWizardFeasibility(form, setForm, step);
  const settingsPersisted = useRecommendationStepAutosave(step, saving, onSave);
  const formProps = { form, setForm };
  const feasibilityProps = { feasibility, feasibilityLoading };

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

        {step === 1 && <InitialAssetsStep {...formProps} currentAssets={currentAssets} />}
        {step === 2 && <GoalTargetStep {...formProps} />}
        {step === 3 && <MonthlyDepositStep {...formProps} {...feasibilityProps} />}
        {step === 4 && <RequiredReturnStep {...formProps} {...feasibilityProps} band={band} />}
        {step === 5 && <InvestorProfileStep {...formProps} />}
        {step === RECOMMENDATION_STEP && (
          <GoalWizardRecommendationStep settingsPersisted={settingsPersisted} onClose={onClose} />
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
