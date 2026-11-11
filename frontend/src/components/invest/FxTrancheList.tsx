import type { FxTranche } from "@/api/invest";
import { fmtKrw, fmtUsd } from "@/utils/format";
import { rateKey } from "@/utils/fxPlanAlerts";

interface Props {
  tranches: FxTranche[];
  /** 이 계획으로 등록한 알림의 목표 키(`rateKey`) */
  planRates: Set<number>;
  /** 같은 목표의 직접 등록한 알림 키 */
  manualRates: Set<number>;
}

/** 분할 환전 구간 목록 — 적립 환전 계획과 추가 환전 항목(plans/123)이 함께 쓴다 */
export default function FxTrancheList({ tranches, planRates, manualRates }: Props) {
  return (
    <ul className="divide-y divide-gray-100 dark:divide-gray-800 rounded-lg border border-gray-100 dark:border-gray-800">
      {tranches.map((t) => (
        <li
          key={t.target_rate ?? t.label}
          className="flex items-center justify-between gap-3 px-3 py-2.5"
        >
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{t.label}</p>
            {t.target_rate !== null && planRates.has(rateKey(t.target_rate)) && (
              <p className="text-xs text-emerald-600 dark:text-emerald-400">알림 등록됨</p>
            )}
            {t.target_rate !== null && manualRates.has(rateKey(t.target_rate)) && (
              <p className="text-xs text-gray-500 dark:text-gray-400">직접 등록한 알림 있음</p>
            )}
          </div>
          <div className="text-right tabular-nums">
            <p className="text-sm font-semibold">{fmtUsd(t.usd, 0)}</p>
            <p className="text-xs text-gray-400 dark:text-gray-500">약 {fmtKrw(t.krw_estimate)}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}
