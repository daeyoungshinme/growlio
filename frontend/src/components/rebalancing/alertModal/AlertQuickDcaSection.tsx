import type { AssetAccount } from "@/api/assets";
import type { RebalancingAlertFormState } from "@/hooks/useRebalancingAlertForm";
import { INPUT_SM } from "@/constants/inputStyles";

const inputClass = `w-full ${INPUT_SM}`;

interface Props {
  form: RebalancingAlertFormState;
  autoExecutionAccounts: AssetAccount[];
  onSwitchToAdvanced: () => void;
}

/** "정기 적립식 자동매수" 빠른 설정 — 매월 며칠/실행 계좌만 고르면 되도록 스케줄/조건/모드/전략은
 * RebalancingAlertModal이 미리 고정값으로 세팅해둔 상태에서 렌더된다 (DCA_AUTO_BUY_THRESHOLD_PCT 등). */
export function AlertQuickDcaSection({ form, autoExecutionAccounts, onSwitchToAdvanced }: Props) {
  return (
    <div className="space-y-4">
      <p className="text-xs text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg px-3 py-2 leading-relaxed">
        이 계좌에 남은 예수금을 매월 지정한 날짜에 포트폴리오 목표 비중대로 자동으로 나눠
        매수합니다. 미리 계좌에 입금해두면, 다음 지정일에 예수금만큼 자동 매수됩니다 (Growlio가 은행
        이체를 대신 해주지는 않습니다). 토스 계좌는 자동매수를 지원하지 않습니다.
      </p>

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          매수 일자
        </label>
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
          <span className="text-xs text-gray-400 dark:text-gray-500">매달 이 날짜에 매수</span>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          실행 계좌
        </label>
        {autoExecutionAccounts.length === 0 ? (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            KIS/키움 연동 계좌가 없습니다. 자산관리에서 계좌를 추가해주세요.
          </p>
        ) : autoExecutionAccounts.length === 1 ? (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-300">
            <span>{autoExecutionAccounts[0].name}</span>
            <span className="text-xs text-gray-400 dark:text-gray-500">(자동 선택)</span>
          </div>
        ) : (
          <select
            className={inputClass}
            value={form.accountId}
            onChange={(e) => form.setAccountId(e.target.value)}
          >
            <option value="">계좌 선택</option>
            {autoExecutionAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        )}
      </div>

      <details className="text-xs text-gray-500 dark:text-gray-400">
        <summary className="cursor-pointer select-none">고급 옵션 (실행 시각)</summary>
        <div className="mt-2">
          <input
            type="time"
            step={300}
            value={form.autoExecutionTime}
            onChange={(e) => form.setAutoExecutionTime(e.target.value)}
            className={inputClass}
          />
          <p className="mt-1">지정 시각에 매수 계획이 생성되고, 대기 후 자동 실행됩니다.</p>
        </div>
      </details>

      <button
        type="button"
        onClick={onSwitchToAdvanced}
        className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 underline underline-offset-2"
      >
        드리프트 조건·매도 등 직접 설정하기 (고급)
      </button>
    </div>
  );
}
