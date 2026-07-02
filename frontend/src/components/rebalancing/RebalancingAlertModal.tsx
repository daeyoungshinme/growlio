import { Bell, BellOff, Loader2, PlayCircle, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { INPUT_SM } from "@/constants/inputStyles";
import Modal from "@/components/common/Modal";
import { type ScheduleType, type TriggerCondition, sendTestRebalancingAlert } from "@/api/alerts";
import { quickExecuteRebalancing, type ExecutionResult } from "@/api/rebalancing";
import { RebalancingResultSection } from "@/components/rebalancing/RebalancingResultSection";
import {
  useRebalancingAlertQueries,
  useRebalancingAlertFormState,
} from "@/hooks/useRebalancingAlertForm";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { invalidateRebalancingHistoryData } from "@/utils/queryInvalidation";
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
  NOTIFY_TIME_OPTIONS,
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
  autoExecutionTime?: string,
  notifyTime?: string,
): string {
  const timeLabel = mode === "AUTO" ? (autoExecutionTime ?? "09:00") : (notifyTime ?? "08:30");
  const when =
    scheduleType === "DAILY"
      ? `매일 ${timeLabel}에`
      : scheduleType === "WEEKLY"
        ? `매주 ${DAYS_KO[dayOfWeek]}요일 ${timeLabel}에`
        : scheduleType === "MONTHLY"
          ? `매월 ${dayOfMonth}일 ${timeLabel}에`
          : scheduleType === "QUARTERLY"
            ? `매 3개월 ${dayOfMonth}일 ${timeLabel}에`
            : scheduleType === "SEMIANNUAL"
              ? `매 6개월 ${dayOfMonth}일 ${timeLabel}에`
              : `매년 ${dayOfMonth}일 ${timeLabel}에`;

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
  const { alert, isLoading, kisExecutionAccounts, marketSignal } =
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
            kisExecutionAccounts={kisExecutionAccounts}
            portfolioId={portfolioId}
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
  kisExecutionAccounts,
  portfolioId,
  onClose,
  marketSignal,
}: {
  alert: RebalancingAlert | null;
  kisExecutionAccounts: AssetAccount[];
  portfolioId: string;
  onClose: () => void;
  marketSignal?: MarketSignalResponse;
}) {
  const form = useRebalancingAlertFormState({
    alert,
    portfolioId,
    onClose,
  });

  const { mode, setAccountId } = form;
  useEffect(() => {
    if (mode !== "AUTO" || kisExecutionAccounts.length !== 1) return;
    setAccountId(kisExecutionAccounts[0].id);
  }, [mode, setAccountId, kisExecutionAccounts]);

  const hasAlert = !!alert;
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [executionResults, setExecutionResults] = useState<ExecutionResult[] | null>(null);
  const queryClient = useQueryClient();

  const testMut = useMutation({
    mutationFn: () => sendTestRebalancingAlert(portfolioId),
    onSuccess: (data) => {
      toast(data.message, data.email_sent || data.push_sent ? "success" : "error");
    },
    onError: (e) => {
      toast(extractErrorMessage(e, "테스트 알림 발송에 실패했습니다"), "error");
    },
  });

  // "지금 테스트 실행" — 저장된(또는 화면에 입력된 미저장) 자동화 설정값으로 실제 스케줄 AUTO
  // 실행과 동일한 로직(실시간 시세 반영, 매도 보유계좌 라우팅, 실시간 잔고 clamp)을 원클릭으로 실행한다.
  const quickExecuteMut = useMutation({
    mutationFn: () =>
      quickExecuteRebalancing(portfolioId, {
        account_id: form.accountId || undefined,
        strategy: form.strategy,
        order_type: form.orderType,
      }),
    onSuccess: (results) => {
      setExecutionResults(results);
      const successCount = results.reduce((sum, r) => sum + r.success_count, 0);
      const failCount = results.reduce((sum, r) => sum + r.fail_count, 0);
      toast(`실행 완료 — 성공 ${successCount}건 · 실패 ${failCount}건`, failCount ? "error" : "success");
      void invalidateRebalancingHistoryData(queryClient);
    },
    onError: (e) => {
      toast(extractErrorMessage(e, "리밸런싱 실행에 실패했습니다"), "error");
    },
  });

  function handleDeleteClick() {
    if (!confirmingDelete) {
      setConfirmingDelete(true);
      setTimeout(() => setConfirmingDelete(false), 3000);
    } else {
      form.deleteMut.mutate();
    }
  }

  return (
    <>
      <div className="p-4 space-y-4 pb-2">
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
                  <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                    {label}
                  </div>
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

        {/* ── 자동 실행 옵션 ── */}
        {form.mode === "AUTO" && (
          <div className="space-y-3 p-4 rounded-xl bg-orange-50 dark:bg-orange-950 border border-orange-200 dark:border-orange-800">
            <p className="text-xs text-orange-600 dark:text-orange-400 font-medium">
              ⚠️ 자동 실행 모드는 실제 매매 주문이 발생합니다.
            </p>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                실행 계좌 (KIS)
              </label>
              {kisExecutionAccounts.length === 0 ? (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  KIS 연동 계좌가 없습니다. 자산관리에서 KIS 계좌를 추가해주세요.
                </p>
              ) : kisExecutionAccounts.length === 1 ? (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-300">
                  <span>{kisExecutionAccounts[0].name}</span>
                  <span className="text-xs text-gray-400 dark:text-gray-500">(자동 선택)</span>
                </div>
              ) : (
                <select
                  className={inputClass}
                  value={form.accountId}
                  onChange={(e) => form.setAccountId(e.target.value)}
                >
                  <option value="">계좌 선택</option>
                  {kisExecutionAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div className="space-y-2">
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
                자동 실행 시각 (KST)
              </label>
              <input
                type="time"
                min="09:00"
                max="15:00"
                step={300}
                value={form.autoExecutionTime}
                onChange={(e) => form.setAutoExecutionTime(e.target.value)}
                className={inputClass}
              />
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                장 중(09:00~15:00 KST) 지정 시각에 자동 실행됩니다.
              </p>
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
              {form.orderType === "LIMIT" && (
                <p className="mt-1.5 text-xs text-amber-600 dark:text-amber-400 leading-relaxed">
                  자동 실행 시 분석 시점의 현재가를 지정가로 사용합니다. 가격 변동으로 미체결될 수 있습니다.
                </p>
              )}
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
              <select
                className={inputClass}
                value={form.marketConditionMode}
                onChange={(e) =>
                  form.setMarketConditionMode(
                    e.target.value as "DISABLED" | "CAUTIOUS" | "STRICT",
                  )
                }
              >
                {MARKET_CONDITION_OPTIONS.map(({ value, label, desc }) => (
                  <option key={value} value={value}>
                    {label} — {desc}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* ── 설명 텍스트 ── */}
        <p className="text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2">
          {buildDescription(
            form.scheduleType,
            form.dayOfWeek,
            form.dayOfMonth,
            form.triggerCondition,
            form.threshold,
            form.mode,
            form.autoExecutionTime,
            form.notifyTime,
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

        {/* ── 테스트 알림 발송 ── */}
        {hasAlert && (
          <button
            onClick={() => testMut.mutate()}
            disabled={testMut.isPending}
            className="w-full flex items-center justify-center gap-2 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
          >
            {testMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
            테스트 알림 발송
          </button>
        )}

        {/* ── 지금 테스트 실행 (AUTO 모드 전용, 실제 매매 발생) ── */}
        {hasAlert && form.mode === "AUTO" && form.accountId && (
          <button
            onClick={() => quickExecuteMut.mutate()}
            disabled={quickExecuteMut.isPending}
            className="w-full flex items-center justify-center gap-2 py-2 text-sm border border-orange-300 dark:border-orange-700 text-orange-600 dark:text-orange-400 rounded-lg hover:bg-orange-50 dark:hover:bg-orange-950 disabled:opacity-50 transition-colors"
          >
            {quickExecuteMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <PlayCircle size={14} />
            )}
            지금 테스트 실행
          </button>
        )}
      </div>
      {/* end p-6 form fields */}

      {executionResults && (
        <Modal title="실행 결과" onClose={() => setExecutionResults(null)} size="md" closeOnBackdrop>
          <div className="p-4 space-y-4 overflow-y-auto">
            <RebalancingResultSection results={executionResults} />
          </div>
        </Modal>
      )}

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
            onClick={handleDeleteClick}
            disabled={form.isPending}
            className={`flex items-center justify-center gap-1.5 px-4 py-2 text-sm rounded-lg disabled:opacity-50 transition-colors ${
              confirmingDelete
                ? "bg-red-600 text-white hover:bg-red-700 border border-red-600"
                : "border border-red-300 text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
            }`}
          >
            {form.deleteMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <BellOff size={14} />
            )}
            {confirmingDelete ? "정말 해제?" : "설정 해제"}
          </button>
        )}
      </div>
    </>
  );
}
