import type { RebalancingAlertFormState } from "@/hooks/useRebalancingAlertForm";
import {
  SCHEDULE_OPTIONS,
  DAYS_KO,
  SCHEDULE_LABEL,
  NEEDS_DAY_OF_MONTH,
} from "@/constants/rebalancingConfig";

interface Props {
  form: RebalancingAlertFormState;
}

export function AlertScheduleSection({ form }: Props) {
  return (
    <>
      {/* ── 알림 주기 ── */}
      <div>
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">실행 주기</p>
        <div className="grid grid-cols-3 gap-1.5">
          {SCHEDULE_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => form.setScheduleType(value)}
              aria-pressed={form.scheduleType === value}
              className={`py-3 rounded-lg text-xs font-medium transition-colors ${
                form.scheduleType === value
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* ── 요일 선택 (WEEKLY) ── */}
      {form.scheduleType === "WEEKLY" && (
        <div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">요일</p>
          <div className="grid grid-cols-7 gap-1">
            {DAYS_KO.map((day, idx) => (
              <button
                key={idx}
                onClick={() => form.setDayOfWeek(idx)}
                aria-pressed={form.dayOfWeek === idx}
                aria-label={`${day}요일`}
                className={`py-2.5 rounded-lg text-xs font-medium transition-colors ${
                  form.dayOfWeek === idx
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
                }`}
              >
                {day}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── 기준 날짜 선택 ── */}
      {NEEDS_DAY_OF_MONTH.includes(form.scheduleType) && (
        <div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">기준 날짜</p>
          <div className="flex items-center gap-2">
            <select
              value={form.dayOfMonth}
              onChange={(e) => form.setDayOfMonth(Number(e.target.value))}
              className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                <option key={d} value={d}>
                  {d}일
                </option>
              ))}
            </select>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {SCHEDULE_LABEL[form.scheduleType]}마다 이 날짜에 실행
            </span>
          </div>
        </div>
      )}
    </>
  );
}
