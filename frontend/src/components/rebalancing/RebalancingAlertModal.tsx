import { Bell, BellOff, Loader2, PlayCircle, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { INPUT_SM } from "@/constants/inputStyles";
import Modal from "@/components/common/Modal";
import {
  sendTestAccountRebalancingAlert,
  sendTestRebalancingAlert,
  updateAlertScope,
} from "@/api/alerts";
import { quickExecuteRebalancing } from "@/api/rebalancing";
import { buildAlertDescription } from "@/utils/rebalancingAlertDescription";
import {
  useRebalancingAlertQueries,
  useRebalancingAlertFormState,
} from "@/hooks/useRebalancingAlertForm";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { invalidatePortfolioData, invalidateRebalancingPlanData } from "@/utils/queryInvalidation";
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
  BUY_WAIT_MINUTES_OPTIONS,
} from "@/constants/rebalancingConfig";

interface Props {
  portfolioId: string;
  portfolioName: string;
  accountIds?: string[] | null;
  /** 지정 시 이 계좌 전용 알림(PER_ACCOUNT 스코프)을 편집한다. */
  targetAccountId?: string;
  targetAccountName?: string;
  /** 연결 계좌가 2개 이상이라 계좌별 독립 설정(PER_ACCOUNT)으로 전환 가능한지 여부. */
  canSwitchToPerAccount?: boolean;
  /** "계좌별로 독립 설정하기" 클릭 후 스코프 전환 성공 시 호출 — 부모가 계좌별 목록 화면으로 전환한다. */
  onSwitchToPerAccount?: () => void;
  onClose: () => void;
}

const inputClass = `w-full ${INPUT_SM}`;

export default function RebalancingAlertModal({
  portfolioId,
  portfolioName,
  accountIds,
  targetAccountId,
  targetAccountName,
  canSwitchToPerAccount,
  onSwitchToPerAccount,
  onClose,
}: Props) {
  const { alert, isLoading, kisExecutionAccounts, targetAccountIsKis, marketSignal } =
    useRebalancingAlertQueries({
      portfolioId,
      accountIds,
      targetAccountId,
    });

  const title = targetAccountName
    ? `리밸런싱 자동화 — ${portfolioName} · ${targetAccountName}`
    : `리밸런싱 자동화 — ${portfolioName}`;

  return (
    <Modal title={title} onClose={onClose} size="md" closeOnBackdrop>
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
            targetAccountIsKis={targetAccountIsKis}
            portfolioId={portfolioId}
            targetAccountId={targetAccountId}
            targetAccountName={targetAccountName}
            canSwitchToPerAccount={canSwitchToPerAccount}
            onSwitchToPerAccount={onSwitchToPerAccount}
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
  targetAccountIsKis,
  portfolioId,
  targetAccountId,
  targetAccountName,
  canSwitchToPerAccount,
  onSwitchToPerAccount,
  onClose,
  marketSignal,
}: {
  alert: RebalancingAlert | null;
  kisExecutionAccounts: AssetAccount[];
  targetAccountIsKis: boolean;
  portfolioId: string;
  targetAccountId?: string;
  targetAccountName?: string;
  canSwitchToPerAccount?: boolean;
  onSwitchToPerAccount?: () => void;
  onClose: () => void;
  marketSignal?: MarketSignalResponse;
}) {
  const form = useRebalancingAlertFormState({
    alert,
    portfolioId,
    targetAccountId,
    onClose,
  });

  const { mode, setAccountId } = form;
  useEffect(() => {
    if (mode !== "AUTO") return;
    // 계좌별 독립 설정(PER_ACCOUNT)은 실행 계좌가 이 화면의 대상 계좌로 고정된다.
    if (targetAccountId) {
      setAccountId(targetAccountId);
      return;
    }
    if (kisExecutionAccounts.length !== 1) return;
    setAccountId(kisExecutionAccounts[0].id);
  }, [mode, setAccountId, kisExecutionAccounts, targetAccountId]);

  const hasAlert = !!alert;
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const queryClient = useQueryClient();

  const testMut = useMutation({
    mutationFn: () =>
      targetAccountId
        ? sendTestAccountRebalancingAlert(portfolioId, targetAccountId)
        : sendTestRebalancingAlert(portfolioId),
    onSuccess: (data) => {
      toast(data.message, data.email_sent || data.push_sent ? "success" : "error");
    },
    onError: (e) => {
      toast(extractErrorMessage(e, "테스트 알림 발송에 실패했습니다"), "error");
    },
  });

  const switchToPerAccountMut = useMutation({
    mutationFn: () => updateAlertScope(portfolioId, "PER_ACCOUNT"),
    onSuccess: () => {
      void invalidatePortfolioData(queryClient);
      toast("계좌별 독립 설정으로 전환되었습니다", "success");
      onSwitchToPerAccount?.();
    },
    onError: (e) => toast(extractErrorMessage(e, "전환에 실패했습니다"), "error"),
  });

  // "지금 테스트 실행" — 저장된(또는 화면에 입력된 미저장) 자동화 설정값으로 실제 스케줄 AUTO와
  // 동일한 파이프라인(드리프트 분석 → 대기 플랜 생성 → 계획 안내 이메일 발송)을 지금 바로 태운다.
  // 즉시 체결이 아니라 매수는 대기시간 후 자동 실행, 매도는 이메일 승인이 필요하다.
  const quickExecuteMut = useMutation({
    mutationFn: () =>
      quickExecuteRebalancing(
        portfolioId,
        {
          account_id: form.accountId || undefined,
          strategy: form.strategy,
          order_type: form.orderType,
        },
        targetAccountId,
      ),
    onSuccess: (result) => {
      const toastType = result.status === "MARKET_BLOCKED" ? "error" : "success";
      toast(result.message, toastType);
      if (result.status === "PLAN_GENERATED") {
        void invalidateRebalancingPlanData(queryClient);
      }
    },
    onError: (e) => {
      toast(extractErrorMessage(e, "계획 생성에 실패했습니다"), "error");
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
            {MODE_OPTIONS.map(({ value: m, label, desc }) => {
              const isAutoDisabled =
                m === "AUTO" &&
                (targetAccountId ? !targetAccountIsKis : kisExecutionAccounts.length === 0);
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
                          ? "KIS 연동 계좌만 자동 실행 가능"
                          : "연동된 KIS 계좌가 없어 자동 실행을 사용할 수 없습니다"}
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

        {/* ── 자동 실행 옵션 ── */}
        {form.mode === "AUTO" && (
          <div className="space-y-3 p-4 rounded-xl bg-orange-50 dark:bg-orange-950 border border-orange-200 dark:border-orange-800">
            <p className="text-xs text-orange-600 dark:text-orange-400 font-medium">
              ⚠️ 자동 실행 모드는 실제 매매 주문이 발생합니다. 조건 충족 시 계획을 이메일로 먼저
              알려드립니다 — 매수는 대기시간 후 자동 실행(취소 가능), 매도는 이메일 승인이 필요하며
              당일 장마감까지 미응답 시 자동 취소됩니다.
            </p>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                실행 계좌 (KIS)
              </label>
              {targetAccountId ? (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-300">
                  <span>{targetAccountName ?? "이 계좌"}</span>
                  <span className="text-xs text-gray-400 dark:text-gray-500">
                    (계좌별 독립 설정 대상)
                  </span>
                </div>
              ) : kisExecutionAccounts.length === 0 ? (
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

            {!targetAccountId && canSwitchToPerAccount && (
              <button
                onClick={() => switchToPerAccountMut.mutate()}
                disabled={switchToPerAccountMut.isPending}
                className="w-full flex items-center justify-center gap-1.5 py-2 text-xs text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-950 disabled:opacity-50 transition-colors"
              >
                {switchToPerAccountMut.isPending && <Loader2 size={12} className="animate-spin" />}
                여러 계좌에 각각 자동 실행 설정하기 →
              </button>
            )}

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
                매수 대기시간
              </label>
              <select
                className={inputClass}
                value={form.buyWaitMinutes}
                onChange={(e) => form.setBuyWaitMinutes(Number(e.target.value))}
              >
                {BUY_WAIT_MINUTES_OPTIONS.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                매수 계획을 이메일로 알린 뒤 이 시간만큼 대기 후 자동 실행됩니다. 그동안 앱이나
                이메일에서 취소할 수 있습니다.
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
                  자동 실행 시 분석 시점의 현재가를 지정가로 사용합니다. 가격 변동으로 미체결될 수
                  있습니다.
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
                  form.setMarketConditionMode(e.target.value as "DISABLED" | "CAUTIOUS" | "STRICT")
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
          {buildAlertDescription(
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
                마지막 트리거: {new Date(alert.last_triggered_at).toLocaleString("ko-KR")}
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

        {/* ── 지금 테스트 실행 (AUTO 모드 전용) — 지금 바로 계획을 생성해 이메일로 보낸다.
             매수는 대기 후 자동 실행, 매도는 이메일 승인이 필요하다 (즉시 체결 아님). ── */}
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
