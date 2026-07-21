import type { AssetAccount } from "@/api/assets";
import type { RebalancingAlertFormState } from "@/hooks/useRebalancingAlertForm";
import { INPUT_SM } from "@/constants/inputStyles";
import { MODE_OPTIONS, NOTIFY_TIME_OPTIONS } from "@/constants/rebalancingConfig";

const inputClass = `w-full ${INPUT_SM}`;

interface Props {
  form: RebalancingAlertFormState;
  targetAccountId?: string;
  targetAccountIsAutoEligible: boolean;
  autoExecutionAccounts: AssetAccount[];
}

export function AlertModeSection({
  form,
  targetAccountId,
  targetAccountIsAutoEligible,
  autoExecutionAccounts,
}: Props) {
  return (
    <>
      {/* ── 실행 모드 ── */}
      <div>
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">실행 모드</p>
        <div className="grid grid-cols-2 gap-2">
          {MODE_OPTIONS.map(({ value: m, label, desc }) => {
            const isAutoDisabled =
              m === "AUTO" &&
              (targetAccountId ? !targetAccountIsAutoEligible : autoExecutionAccounts.length === 0);
            return (
              <label
                key={m}
                className={`flex items-start gap-2 p-3 rounded-lg border transition-colors ${
                  isAutoDisabled
                    ? "opacity-50 cursor-not-allowed border-gray-300 dark:border-gray-600"
                    : `cursor-pointer ${
                        form.mode === m
                          ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
                          : "border-gray-300 dark:border-gray-600 hover:border-gray-400"
                      }`
                }`}
              >
                <input
                  type="radio"
                  name="mode"
                  value={m}
                  checked={form.mode === m}
                  disabled={isAutoDisabled}
                  onChange={() => form.setMode(m)}
                  className="mt-0.5 accent-blue-600"
                />
                <div>
                  <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                    {label}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{desc}</div>
                  {isAutoDisabled && (
                    <div className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">
                      {targetAccountId
                        ? "KIS/키움 연동 계좌만 자동 실행 가능"
                        : "연동된 KIS/키움 계좌가 없어 자동 실행을 사용할 수 없습니다"}
                    </div>
                  )}
                </div>
              </label>
            );
          })}
        </div>
      </div>

      {/* ── NOTIFY 모드 알림 시각 ── */}
      {form.mode === "NOTIFY" && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            알림 시각 (KST)
          </label>
          <select
            value={form.notifyTime}
            onChange={(e) => form.setNotifyTime(e.target.value)}
            className={inputClass}
          >
            {NOTIFY_TIME_OPTIONS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
            매일 지정 시각에 알림을 확인합니다. 기본값: 08:30
          </p>
        </div>
      )}
    </>
  );
}
