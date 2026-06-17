import { Bell, BellOff, Loader2 } from "lucide-react";
import { INPUT_SM } from "@/constants/inputStyles";
import Modal from "@/components/common/Modal";
import { type ScheduleType, type TriggerCondition } from "@/api/alerts";
import {
  useRebalancingAlertQueries,
  useRebalancingAlertFormState,
} from "@/hooks/useRebalancingAlertForm";
import MarketSignalLevelBadge from "@/components/rebalancing/MarketSignalLevelBadge";
import {
  SCHEDULE_OPTIONS,
  DAYS_KO,
  SCHEDULE_LABEL,
  NEEDS_DAY_OF_MONTH,
  TRIGGER_CONDITION_OPTIONS,
  MODE_OPTIONS,
  STRATEGY_OPTIONS,
  MARKET_CONDITION_OPTIONS,
} from "@/constants/rebalancingConfig";

interface Props {
  portfolioId: string;
  portfolioName: string;
  accountIds?: string[] | null;
  onClose: () => void;
}

function buildDescription(
  scheduleType: ScheduleType,
  dayOfWeek: number,
  dayOfMonth: number,
  triggerCondition: TriggerCondition,
  threshold: number,
  mode: "NOTIFY" | "AUTO",
): string {
  const when =
    scheduleType === "DAILY"
      ? "매일 08:30에"
      : scheduleType === "WEEKLY"
        ? `매주 ${DAYS_KO[dayOfWeek]}요일 08:30에`
        : scheduleType === "MONTHLY"
          ? `매월 ${dayOfMonth}일 08:30에`
          : scheduleType === "QUARTERLY"
            ? `매 3개월 ${dayOfMonth}일 08:30에`
            : scheduleType === "SEMIANNUAL"
              ? `매 6개월 ${dayOfMonth}일 08:30에`
              : `매년 ${dayOfMonth}일 08:30에`;

  const action = mode === "AUTO" ? "자동으로 리밸런싱을 실행합니다." : "알림을 받습니다.";

  if (triggerCondition === "DRIFT_ONLY") {
    return `비중이 ±${threshold.toFixed(1)}% 이상 이탈 시 ${when} ${action}`;
  }
  if (triggerCondition === "SCHEDULE_ONLY") {
    return `${when} 리밸런싱 현황 리포트를 받습니다.`;
  }
  return `${when} 정기 리포트를 받으며, 비중이 ±${threshold.toFixed(1)}% 이탈 시 즉시 ${action}`;
}

const inputClass = `w-full ${INPUT_SM}`;

export default function RebalancingAlertModal({
  portfolioId,
  portfolioName,
  accountIds,
  onClose,
}: Props) {
  const { alert, isLoading, brokerAccounts, kisAccounts, marketSignal } =
    useRebalancingAlertQueries({ portfolioId, accountIds });

  return (
    <Modal title={`리밸런싱 자동화 — ${portfolioName}`} onClose={onClose} size="sm" closeOnBackdrop>
      <div className="flex-1 overflow-y-auto overscroll-contain">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Loader2 size={20} className="animate-spin text-gray-400" />
          </div>
        ) : (
          <AlertFormBody
            key={alert?.id ?? "new"}
            alert={alert}
            brokerAccounts={brokerAccounts}
            kisAccounts={kisAccounts}
            portfolioId={portfolioId}
            accountIds={accountIds}
            onClose={onClose}
            marketSignal={marketSignal}
          />
        )}
      </div>
    </Modal>
  );
}

import type { RebalancingAlert } from "@/api/alerts";
import type { AssetAccount } from "@/api/assets";
import type { MarketSignalResponse } from "@/api/marketSignals";

function AlertFormBody({
  alert,
  brokerAccounts,
  kisAccounts,
  portfolioId,
  accountIds,
  onClose,
  marketSignal,
}: {
  alert: RebalancingAlert | null;
  brokerAccounts: AssetAccount[];
  kisAccounts: AssetAccount[];
  portfolioId: string;
  accountIds?: string[] | null;
  onClose: () => void;
  marketSignal?: MarketSignalResponse;
}) {
  const form = useRebalancingAlertFormState({
    alert,
    portfolioId,
    accountIds,
    kisAccounts,
    onClose,
  });

  const hasAlert = !!alert;

  return (
    <>
      <div className="p-6 space-y-5 pb-2">
        {/* ── 알림 주기 ── */}
        <div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">실행 주기</p>
          <div className="flex flex-wrap gap-1.5">
            {SCHEDULE_OPTIONS.map(({ value, label }) => (
              <button
                key={value}
                onClick={() => form.setScheduleType(value)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
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
                  className={`py-1.5 rounded-lg text-xs font-medium transition-colors ${
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

        {/* ── 알림 조건 ── */}
        <div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">실행 조건</p>
          <div className="space-y-2">
            {TRIGGER_CONDITION_OPTIONS.map(({ value, label, desc }) => (
              <label key={value} className="flex items-start gap-2.5 cursor-pointer">
                <input
                  type="radio"
                  checked={form.triggerCondition === value}
                  onChange={() => form.setTriggerCondition(value)}
                  className="mt-0.5 text-blue-600"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">
                  {label}
                  <span className="block text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                    {desc}
                  </span>
                </span>
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
          </div>
        )}

        {/* ── 실행 모드 ── */}
        <div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">실행 모드</p>
          <div className="grid grid-cols-2 gap-2">
            {MODE_OPTIONS.map(({ value: m, label, desc }) => (
              <label
                key={m}
                className={`flex items-start gap-2 p-3 rounded-lg border cursor-pointer transition-colors ${
                  form.mode === m
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
                    : "border-gray-300 dark:border-gray-600 hover:border-gray-400"
                }`}
              >
                <input
                  type="radio"
                  name="mode"
                  value={m}
                  checked={form.mode === m}
                  onChange={() => form.setMode(m)}
                  className="mt-0.5 accent-blue-600"
                />
                <div>
                  <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                    {label}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{desc}</div>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* ── 자동 실행 옵션 ── */}
        {form.mode === "AUTO" && (
          <div className="space-y-3 p-4 rounded-xl bg-orange-50 dark:bg-orange-950 border border-orange-200 dark:border-orange-800">
            <p className="text-xs text-orange-600 dark:text-orange-400 font-medium">
              ⚠️ 자동 실행 모드는 실제 매매 주문이 발생합니다.
            </p>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                실행 계좌 (KIS/키움)
              </label>
              <select
                className={inputClass}
                value={form.accountId}
                onChange={(e) => form.setAccountId(e.target.value)}
              >
                <option value="">계좌 선택</option>
                {brokerAccounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {STRATEGY_OPTIONS.map(({ value: s, label, desc }) => (
                <label
                  key={s}
                  className={`flex items-start gap-2 p-2.5 rounded-lg border cursor-pointer transition-colors ${
                    form.strategy === s
                      ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
                      : "border-gray-300 dark:border-gray-600 hover:border-gray-400"
                  }`}
                >
                  <input
                    type="radio"
                    name="strategy"
                    value={s}
                    checked={form.strategy === s}
                    onChange={() => form.setStrategy(s)}
                    className="mt-0.5 accent-blue-600"
                  />
                  <div>
                    <div className="text-xs font-medium text-gray-800 dark:text-gray-200">
                      {label}
                    </div>
                    <div className="text-xs text-gray-400 dark:text-gray-500">{desc}</div>
                  </div>
                </label>
              ))}
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                주문 유형
              </label>
              <select
                className={inputClass}
                value={form.orderType}
                onChange={(e) => form.setOrderType(e.target.value as "MARKET" | "LIMIT")}
              >
                <option value="MARKET">시장가</option>
                <option value="LIMIT">지정가</option>
              </select>
            </div>

            {/* ── 시장 신호 연동 ── */}
            <div className="pt-1 border-t border-orange-200/30 dark:border-orange-800/30">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  시장 신호 연동
                </p>
                {marketSignal && (
                  <div className="flex items-center gap-1.5 text-xs text-gray-400">
                    현재: <MarketSignalLevelBadge level={marketSignal.composite_level} size="xs" />
                  </div>
                )}
              </div>
              <div className="space-y-1.5">
                {MARKET_CONDITION_OPTIONS.map(({ value, label, desc }) => (
                  <label
                    key={value}
                    className={`flex items-start gap-2 p-2 rounded-lg border cursor-pointer transition-colors ${
                      form.marketConditionMode === value
                        ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
                        : "border-gray-300 dark:border-gray-600 hover:border-gray-400"
                    }`}
                  >
                    <input
                      type="radio"
                      name="market_condition_mode"
                      value={value}
                      checked={form.marketConditionMode === value}
                      onChange={() => form.setMarketConditionMode(value)}
                      className="mt-0.5 accent-blue-600"
                    />
                    <div>
                      <div className="text-xs font-medium text-gray-800 dark:text-gray-200">
                        {label}
                      </div>
                      <div className="text-xs text-gray-400 dark:text-gray-500">{desc}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── 예수금 입금 감지 ── */}
        <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-1">
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                예수금 입금 감지
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                입금 확인 시 위 설정(알림/자동실행)으로 비중 배분 매수
              </p>
            </div>
            <button
              role="switch"
              aria-checked={form.depositTriggerEnabled}
              onClick={() => form.setDepositTriggerEnabled((v) => !v)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                form.depositTriggerEnabled ? "bg-blue-600" : "bg-gray-300 dark:bg-gray-600"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  form.depositTriggerEnabled ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>

          <div
            className={`grid transition-all duration-200 ${form.depositTriggerEnabled ? "grid-rows-[1fr] mt-3" : "grid-rows-[0fr]"}`}
          >
            <div className="overflow-hidden">
              <div className="space-y-3 p-3 rounded-xl bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800">
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    감시 계좌 (KIS)
                  </label>
                  <select
                    className={inputClass}
                    value={form.depositTriggerAccountId}
                    onChange={(e) => form.setDepositTriggerAccountId(e.target.value)}
                  >
                    <option value="">계좌 선택</option>
                    {kisAccounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                        {a.deposit_krw != null
                          ? ` — 예수금 ${a.deposit_krw.toLocaleString("ko-KR")}원`
                          : ""}
                      </option>
                    ))}
                  </select>
                  {kisAccounts.length === 0 && (
                    <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                      {accountIds != null
                        ? "이 포트폴리오에 연결된 KIS 계좌가 없습니다. 포트폴리오 설정에서 KIS 계좌를 연결해주세요."
                        : "KIS 계좌가 없습니다. 자산관리에서 KIS 계좌를 추가해주세요."}
                    </p>
                  )}
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    최소 감지 금액 (KRW)
                  </label>
                  <input
                    type="number"
                    min={10_000}
                    step={10_000}
                    value={form.depositTriggerMinAmount}
                    onChange={(e) => form.setDepositTriggerMinAmount(Number(e.target.value))}
                    className={inputClass}
                    placeholder="예: 100000"
                  />
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    이 금액 이상 입금 시에만 동작 (최소 10,000원)
                  </p>
                </div>

                {alert?.last_deposit_checked_at && (
                  <p className="text-xs text-blue-600 dark:text-blue-400">
                    마지막 확인: {new Date(alert.last_deposit_checked_at).toLocaleString("ko-KR")}
                    {alert.last_known_deposit_krw != null && (
                      <span className="block">
                        기준 예수금: {alert.last_known_deposit_krw.toLocaleString("ko-KR")}원
                      </span>
                    )}
                  </p>
                )}
              </div>
            </div>
            {/* end overflow-hidden */}
          </div>
          {/* end grid animation wrapper */}
        </div>

        {/* ── 설명 텍스트 ── */}
        <p className="text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2">
          {buildDescription(
            form.scheduleType,
            form.dayOfWeek,
            form.dayOfMonth,
            form.triggerCondition,
            form.threshold,
            form.mode,
          )}
        </p>

        {/* ── 현재 설정 표시 ── */}
        {hasAlert && (
          <div className="rounded-lg bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 p-3 text-xs text-blue-700 dark:text-blue-300">
            현재 설정이 활성화되어 있습니다.
            {alert.last_triggered_at && (
              <span className="block mt-0.5 text-blue-500">
                마지막 실행: {new Date(alert.last_triggered_at).toLocaleString("ko-KR")}
              </span>
            )}
          </div>
        )}
      </div>
      {/* end p-6 form fields */}

      {/* ── 버튼 ── */}
      <div className="sticky bottom-0 bg-white dark:bg-gray-900 px-6 py-4 border-t border-gray-100 dark:border-gray-700 flex gap-3">
        <button
          onClick={() => form.upsertMut.mutate()}
          disabled={form.isPending}
          aria-busy={form.upsertMut.isPending}
          className="flex-1 flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {form.upsertMut.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Bell size={14} />
          )}
          {hasAlert ? "설정 업데이트" : "자동화 설정"}
        </button>
        {hasAlert && (
          <button
            onClick={() => form.deleteMut.mutate()}
            disabled={form.isPending}
            className="flex items-center justify-center gap-1.5 px-4 py-2 text-sm border border-red-300 text-red-600 rounded-lg hover:bg-red-50 dark:hover:bg-red-950 disabled:opacity-50 transition-colors"
          >
            {form.deleteMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <BellOff size={14} />
            )}
            설정 해제
          </button>
        )}
      </div>
    </>
  );
}
