import { Link } from "react-router-dom";
import FormInput from "@/components/common/FormInput";
import type { GoalFeasibilityPreview } from "@/api/invest";
import { fmtKrw, fmtKrwPreview, fmtPct } from "@/utils/format";
import type { GoalFeasibilityBand } from "@/utils/goalFeasibility";
import GoalWizardLoading from "./GoalWizardLoading";
import type { StepFormProps } from "./GoalWizardInputSteps";

// 백엔드 DEPOSIT_GUIDE_PRESET_RETURNS_PCT(4/7/10%)와 배열 순서로 매칭되는 표시용 레이블
const DEPOSIT_GUIDE_PRESET_LABELS = ["보수적", "중립", "공격적"];

interface FeasibilityProps {
  feasibility: GoalFeasibilityPreview | undefined;
  feasibilityLoading: boolean;
}

/** 3단계 — 월 적립액·연간 입금 목표. 가정 수익률별 필요 적립액 가이드로 바로 채울 수 있다. */
export function MonthlyDepositStep({
  form,
  setForm,
  feasibility,
  feasibilityLoading,
}: StepFormProps & FeasibilityProps) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500 dark:text-gray-400">
        매달 얼마씩 적립할 계획인가요? 연간 입금 목표는 자동으로 계산되며 직접 조정할 수 있습니다.
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
          form.annual_deposit_goal ? fmtKrwPreview(Number(form.annual_deposit_goal)) : undefined
        }
        hint="월 적립액 × 12로 자동 계산 — 대시보드 입금 달성률에 표시, 직접 조정 가능"
      />

      <div className="pt-1 space-y-2">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          얼마를 적립해야 할지 감이 안 온다면, 가정 수익률별 필요 적립액을 참고해 바로 채워보세요.
        </p>
        {feasibilityLoading && <GoalWizardLoading text="계산하고 있어요..." />}
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
  );
}

/** 4단계 — 입력한 적립액 기준 필요 연수익률과 실현 가능성 밴드, 목표 연수익률 입력. */
export function RequiredReturnStep({
  form,
  setForm,
  feasibility,
  feasibilityLoading,
  band,
}: StepFormProps & FeasibilityProps & { band: GoalFeasibilityBand | null }) {
  return (
    <div className="space-y-3">
      {feasibilityLoading && <GoalWizardLoading text="필요 수익률을 계산하고 있어요..." />}
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
        to="/rebalancing?rtab=추천"
        className="block text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
      >
        추천 포트폴리오 보러가기 →
      </Link>
    </div>
  );
}
