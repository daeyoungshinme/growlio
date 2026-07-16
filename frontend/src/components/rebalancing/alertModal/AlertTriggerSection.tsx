import type { RebalancingAlertFormState } from "@/hooks/useRebalancingAlertForm";
import { TRIGGER_CONDITION_OPTIONS } from "@/constants/rebalancingConfig";

interface Props {
  form: RebalancingAlertFormState;
}

export function AlertTriggerSection({ form }: Props) {
  return (
    <>
      {/* ── 알림 조건 ── */}
      <div>
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">실행 조건</p>
        <div className="space-y-2">
          {TRIGGER_CONDITION_OPTIONS.map(({ value, label, desc }) => (
            <label
              key={value}
              className={`flex items-start gap-2 p-3 rounded-lg border cursor-pointer transition-colors ${
                form.triggerCondition === value
                  ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
                  : "border-gray-300 dark:border-gray-600 hover:border-gray-400"
              }`}
            >
              <input
                type="radio"
                checked={form.triggerCondition === value}
                onChange={() => form.setTriggerCondition(value)}
                className="mt-0.5 accent-blue-600 shrink-0"
              />
              <div>
                <div className="text-sm font-medium text-gray-800 dark:text-gray-200">{label}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* ── 임계값 슬라이더 ── */}
      {(form.triggerCondition === "DRIFT_ONLY" || form.triggerCondition === "BOTH") && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            이탈 임계값
          </label>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={1}
              max={20}
              step={0.5}
              value={form.threshold}
              onChange={(e) => form.setThreshold(parseFloat(e.target.value))}
              className="flex-1"
            />
            <span className="text-sm font-semibold text-blue-600 dark:text-blue-400 w-14 text-right">
              ±{form.threshold.toFixed(1)}%
            </span>
          </div>
          {form.isNewAlert && form.threshold === form.recommendedThreshold && (
            <p className="mt-1.5 text-xs text-gray-400 dark:text-gray-500">
              계좌 유형 기반 추천값: {form.recommendedThreshold.toFixed(1)}% · 직접 조정 가능
            </p>
          )}
        </div>
      )}
    </>
  );
}
