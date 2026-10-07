import type { Dispatch, SetStateAction } from "react";
import FormInput from "@/components/common/FormInput";
import type { GoalRiskTolerance } from "@/api/settings";
import { RISK_TOLERANCE_OPTIONS } from "@/constants/goalRiskTolerance";
import { fmtKrw, fmtKrwPreview } from "@/utils/format";
import type { GoalForm } from "@/hooks/useGoalSettings";

export interface StepFormProps {
  form: GoalForm;
  setForm: Dispatch<SetStateAction<GoalForm>>;
}

/** 1단계 — 목표 계산의 시작점이 되는 현재 자산. */
export function InitialAssetsStep({
  form,
  setForm,
  currentAssets,
}: StepFormProps & { currentAssets: number | null }) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500 dark:text-gray-400">
        목표 계산의 시작점이 되는 현재 자산입니다. 비워두면 최근 자산 스냅샷이 자동으로 사용됩니다.
      </p>
      <FormInput
        label="투자 시작시점 자산 (원)"
        type="number"
        inputMode="numeric"
        value={form.goal_initial_amount}
        onChange={(e) => setForm((f) => ({ ...f, goal_initial_amount: e.target.value }))}
        placeholder={currentAssets != null ? String(Math.round(currentAssets)) : "100000000"}
        preview={
          form.goal_initial_amount ? fmtKrwPreview(Number(form.goal_initial_amount)) : undefined
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
  );
}

/** 2단계 — 목표 금액과 시점. */
export function GoalTargetStep({ form, setForm }: StepFormProps) {
  return (
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
  );
}

/** 5단계 — 추천에 쓰이는 출생연도·투자성향·배당목표(모두 선택 입력). */
export function InvestorProfileStep({ form, setForm }: StepFormProps) {
  return (
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
          목표 달성에 필요한 최소 수익률보다 더 높은 수익률을 목표로 삼을수록 변동성도 커집니다.
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
          form.annual_dividend_goal ? fmtKrwPreview(Number(form.annual_dividend_goal)) : undefined
        }
        hint="설정하면 추천 포트폴리오가 배당수익률도 함께 고려합니다"
      />
    </div>
  );
}
