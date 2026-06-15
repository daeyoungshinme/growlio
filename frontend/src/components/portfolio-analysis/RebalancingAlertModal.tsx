import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellOff, Loader2 } from "lucide-react";
import { INPUT_SM } from "@/constants/inputStyles";
import Modal from "@/components/common/Modal";
import {
  fetchRebalancingAlert,
  upsertRebalancingAlert,
  deleteRebalancingAlert,
  type ScheduleType,
  type MarketConditionMode,
} from "@/api/alerts";
import { fetchAccounts } from "@/api/assets";
import { fetchMarketSignal } from "@/api/marketSignals";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateRebalancingAlertData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { extractErrorMessage, getHttpStatus } from "@/utils/error";
import MarketSignalLevelBadge from "@/components/rebalancing/MarketSignalLevelBadge";

interface Props {
  portfolioId: string;
  portfolioName: string;
  onClose: () => void;
}

const SCHEDULE_OPTIONS: { value: ScheduleType; label: string }[] = [
  { value: "DAILY", label: "매일" },
  { value: "WEEKLY", label: "매주" },
  { value: "MONTHLY", label: "매월" },
  { value: "QUARTERLY", label: "3개월" },
  { value: "SEMIANNUAL", label: "6개월" },
  { value: "ANNUAL", label: "1년" },
];

const DAYS_KO = ["월", "화", "수", "목", "금", "토", "일"];

const SCHEDULE_LABEL: Record<ScheduleType, string> = {
  DAILY: "매일",
  WEEKLY: "매주",
  MONTHLY: "매월",
  QUARTERLY: "매 3개월",
  SEMIANNUAL: "매 6개월",
  ANNUAL: "매년",
};

function buildDescription(
  scheduleType: ScheduleType,
  dayOfWeek: number,
  dayOfMonth: number,
  onlyWhenDrift: boolean,
  threshold: number,
  mode: "NOTIFY" | "AUTO",
): string {
  const when =
    scheduleType === "DAILY"
      ? "매일 18:30에"
      : scheduleType === "WEEKLY"
        ? `매주 ${DAYS_KO[dayOfWeek]}요일 18:30에`
        : scheduleType === "MONTHLY"
          ? `매월 ${dayOfMonth}일 18:30에`
          : scheduleType === "QUARTERLY"
            ? `매 3개월 ${dayOfMonth}일 18:30에`
            : scheduleType === "SEMIANNUAL"
              ? `매 6개월 ${dayOfMonth}일 18:30에`
              : `매년 ${dayOfMonth}일 18:30에`;

  const action = mode === "AUTO" ? "자동으로 리밸런싱을 실행합니다." : "알림을 받습니다.";

  return onlyWhenDrift
    ? `비중이 ±${threshold.toFixed(1)}% 이상 이탈 시 ${when} ${action}`
    : `${when} 리밸런싱 현황 리포트를 받습니다.`;
}

const NEEDS_DAY_OF_MONTH: ScheduleType[] = ["MONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL"];

const inputClass = `w-full ${INPUT_SM}`;

import type { RebalancingAlert } from "@/api/alerts";
import type { AssetAccount } from "@/api/assets";
import type { MarketSignalResponse } from "@/api/marketSignals";
import type { QueryClient } from "@tanstack/react-query";

export default function RebalancingAlertModal({ portfolioId, portfolioName, onClose }: Props) {
  const qc = useQueryClient();

  const { data: alert, isLoading } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlert(portfolioId),
    queryFn: () => fetchRebalancingAlert(portfolioId),
    staleTime: STALE_TIME.MEDIUM,
    retry: (failureCount, error: unknown) => {
      const status = getHttpStatus(error);
      return status === 404 ? false : failureCount < 2;
    },
  });

  const { data: accounts = [] } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
    staleTime: STALE_TIME.MEDIUM,
  });

  const { data: marketSignal } = useQuery({
    queryKey: QUERY_KEYS.marketSignal,
    queryFn: fetchMarketSignal,
    staleTime: STALE_TIME.LONG,
  });

  const brokerAccounts = accounts.filter(
    (a) => (a.asset_type === "STOCK_KIS" || a.asset_type === "STOCK_KIWOOM") && a.is_active,
  );

  return (
    <Modal title={`리밸런싱 자동화 — ${portfolioName}`} onClose={onClose} size="sm" closeOnBackdrop>
      <div className="p-6 space-y-5">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Loader2 size={20} className="animate-spin text-gray-400" />
          </div>
        ) : (
          <AlertFormBody
            key={alert?.id ?? "new"}
            alert={alert ?? null}
            brokerAccounts={brokerAccounts}
            portfolioId={portfolioId}
            qc={qc}
            onClose={onClose}
            marketSignal={marketSignal}
          />
        )}
      </div>
    </Modal>
  );
}

function AlertFormBody({
  alert,
  brokerAccounts,
  portfolioId,
  qc,
  onClose,
  marketSignal,
}: {
  alert: RebalancingAlert | null;
  brokerAccounts: AssetAccount[];
  portfolioId: string;
  qc: QueryClient;
  onClose: () => void;
  marketSignal?: MarketSignalResponse;
}) {
  const [scheduleType, setScheduleType] = useState<ScheduleType>(alert?.schedule_type ?? "DAILY");
  const [dayOfWeek, setDayOfWeek] = useState(alert?.schedule_day_of_week ?? 0);
  const [dayOfMonth, setDayOfMonth] = useState(alert?.schedule_day_of_month ?? 1);
  const [onlyWhenDrift, setOnlyWhenDrift] = useState(alert?.only_when_drift ?? true);
  const [threshold, setThreshold] = useState(alert?.threshold_pct ?? 5);
  const [mode, setMode] = useState<"NOTIFY" | "AUTO">(alert?.mode ?? "NOTIFY");
  const [strategy, setStrategy] = useState<"FULL" | "BUY_ONLY">(alert?.strategy ?? "BUY_ONLY");
  const [accountId, setAccountId] = useState<string>(alert?.account_id ?? "");
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT">(alert?.order_type ?? "MARKET");
  const [marketConditionMode, setMarketConditionMode] = useState<MarketConditionMode>(
    alert?.market_condition_mode ?? "DISABLED",
  );

  const upsertMut = useMutation({
    mutationFn: () =>
      upsertRebalancingAlert(portfolioId, {
        threshold_pct: threshold,
        schedule_type: scheduleType,
        schedule_day_of_week: scheduleType === "WEEKLY" ? dayOfWeek : null,
        schedule_day_of_month: NEEDS_DAY_OF_MONTH.includes(scheduleType) ? dayOfMonth : null,
        only_when_drift: onlyWhenDrift,
        mode,
        strategy,
        account_id: mode === "AUTO" && accountId ? accountId : null,
        order_type: orderType,
        market_condition_mode: mode === "AUTO" ? marketConditionMode : "DISABLED",
      }),
    onSuccess: () => {
      invalidateRebalancingAlertData(qc, portfolioId);
      toast("설정이 저장되었습니다", "success");
      onClose();
    },
    onError: (e) => toast(extractErrorMessage(e, "설정 저장에 실패했습니다")),
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteRebalancingAlert(portfolioId),
    onSuccess: () => {
      invalidateRebalancingAlertData(qc, portfolioId);
      toast("설정이 해제되었습니다", "success");
      onClose();
    },
    onError: (e) => toast(extractErrorMessage(e, "설정 해제에 실패했습니다")),
  });

  const isPending = upsertMut.isPending || deleteMut.isPending;
  const hasAlert = !!alert;

  return (
    <>
      {/* ── 알림 주기 ── */}
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">실행 주기</p>
              <div className="flex flex-wrap gap-1.5">
                {SCHEDULE_OPTIONS.map(({ value, label }) => (
                  <button
                    key={value}
                    onClick={() => setScheduleType(value)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      scheduleType === value
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
            {scheduleType === "WEEKLY" && (
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">요일</p>
                <div className="flex gap-1">
                  {DAYS_KO.map((day, idx) => (
                    <button
                      key={idx}
                      onClick={() => setDayOfWeek(idx)}
                      className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                        dayOfWeek === idx
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

            {/* ── 기준 날짜 선택 (MONTHLY/QUARTERLY/SEMIANNUAL/ANNUAL) ── */}
            {NEEDS_DAY_OF_MONTH.includes(scheduleType) && (
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  기준 날짜
                </p>
                <div className="flex items-center gap-2">
                  <select
                    value={dayOfMonth}
                    onChange={(e) => setDayOfMonth(Number(e.target.value))}
                    className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                      <option key={d} value={d}>
                        {d}일
                      </option>
                    ))}
                  </select>
                  <span className="text-xs text-gray-400 dark:text-gray-500">
                    {SCHEDULE_LABEL[scheduleType]}마다 이 날짜에 실행
                  </span>
                </div>
              </div>
            )}

            {/* ── 알림 조건 ── */}
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">실행 조건</p>
              <div className="space-y-2">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="radio"
                    checked={onlyWhenDrift}
                    onChange={() => setOnlyWhenDrift(true)}
                    className="mt-0.5 text-blue-600"
                  />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    비중 이탈 시에만
                    <span className="block text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                      이탈 종목이 있을 때만 동작합니다
                    </span>
                  </span>
                </label>
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="radio"
                    checked={!onlyWhenDrift}
                    onChange={() => setOnlyWhenDrift(false)}
                    className="mt-0.5 text-blue-600"
                  />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    주기마다 항상
                    <span className="block text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                      이탈 여부와 관계없이 주기마다 리포트를 받습니다
                    </span>
                  </span>
                </label>
              </div>
            </div>

            {/* ── 임계값 슬라이더 (이탈 시에만 표시) ── */}
            {onlyWhenDrift && (
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
                    value={threshold}
                    onChange={(e) => setThreshold(parseFloat(e.target.value))}
                    className="flex-1"
                  />
                  <span className="text-sm font-semibold text-blue-600 dark:text-blue-400 w-14 text-right">
                    ±{threshold.toFixed(1)}%
                  </span>
                </div>
              </div>
            )}

            {/* ── 실행 모드 ── */}
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">실행 모드</p>
              <div className="grid grid-cols-2 gap-2">
                {(["NOTIFY", "AUTO"] as const).map((m) => (
                  <label
                    key={m}
                    className={`flex items-start gap-2 p-3 rounded-lg border cursor-pointer transition-colors ${
                      mode === m
                        ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
                        : "border-gray-300 dark:border-gray-600 hover:border-gray-400"
                    }`}
                  >
                    <input
                      type="radio"
                      name="mode"
                      value={m}
                      checked={mode === m}
                      onChange={() => setMode(m)}
                      className="mt-0.5 accent-blue-600"
                    />
                    <div>
                      <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                        {m === "NOTIFY" ? "알림만 (권장)" : "자동 실행"}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        {m === "NOTIFY" ? "이메일로 알림 수신" : "조건 충족 시 주문 자동 실행"}
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* ── 자동 실행 옵션 (AUTO 모드) ── */}
            {mode === "AUTO" && (
              <div className="space-y-3 p-3 rounded-xl bg-orange-50 dark:bg-orange-950 border border-orange-200 dark:border-orange-800">
                <p className="text-xs text-orange-600 dark:text-orange-400 font-medium">
                  ⚠️ 자동 실행 모드는 실제 매매 주문이 발생합니다.
                </p>

                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                    실행 계좌 (KIS/키움)
                  </label>
                  <select
                    className={inputClass}
                    value={accountId}
                    onChange={(e) => setAccountId(e.target.value)}
                  >
                    <option value="">계좌 선택</option>
                    {brokerAccounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  {(["BUY_ONLY", "FULL"] as const).map((s) => (
                    <label
                      key={s}
                      className={`flex items-start gap-2 p-2.5 rounded-lg border cursor-pointer transition-colors ${
                        strategy === s
                          ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
                          : "border-gray-300 dark:border-gray-600 hover:border-gray-400"
                      }`}
                    >
                      <input
                        type="radio"
                        name="strategy"
                        value={s}
                        checked={strategy === s}
                        onChange={() => setStrategy(s)}
                        className="mt-0.5 accent-blue-600"
                      />
                      <div>
                        <div className="text-xs font-medium text-gray-800 dark:text-gray-200">
                          {s === "BUY_ONLY" ? "매수만 (권장)" : "매도+매수"}
                        </div>
                        <div className="text-xs text-gray-400 dark:text-gray-500">
                          {s === "BUY_ONLY" ? "세금 절감" : "완전 리밸런싱"}
                        </div>
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
                    value={orderType}
                    onChange={(e) => setOrderType(e.target.value as "MARKET" | "LIMIT")}
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
                        현재:
                        <MarketSignalLevelBadge level={marketSignal.composite_level} size="xs" />
                      </div>
                    )}
                  </div>
                  <div className="space-y-1.5">
                    {(
                      [
                        {
                          value: "DISABLED" as MarketConditionMode,
                          label: "신호 무시",
                          desc: "시장 상황과 무관하게 자동 실행",
                        },
                        {
                          value: "CAUTIOUS" as MarketConditionMode,
                          label: "신중",
                          desc: "고위험(RED) 신호 시 자동 실행 중단",
                        },
                        {
                          value: "STRICT" as MarketConditionMode,
                          label: "엄격",
                          desc: "중위험(YELLOW) 이상에서 자동 실행 중단",
                        },
                      ] as const
                    ).map(({ value, label, desc }) => (
                      <label
                        key={value}
                        className={`flex items-start gap-2 p-2 rounded-lg border cursor-pointer transition-colors ${
                          marketConditionMode === value
                            ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
                            : "border-gray-300 dark:border-gray-600 hover:border-gray-400"
                        }`}
                      >
                        <input
                          type="radio"
                          name="market_condition_mode"
                          value={value}
                          checked={marketConditionMode === value}
                          onChange={() => setMarketConditionMode(value)}
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

            {/* ── 설명 텍스트 ── */}
            <p className="text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2">
              {buildDescription(scheduleType, dayOfWeek, dayOfMonth, onlyWhenDrift, threshold, mode)}
            </p>

            {/* ── 현재 설정 표시 ── */}
            {hasAlert && (
              <div className="rounded-lg bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 p-3 text-xs text-blue-700 dark:text-blue-300">
                현재 설정이 활성화되어 있습니다.
                {alert.last_triggered_at && (
                  <span className="block mt-0.5 text-blue-500">
                    마지막 실행:{" "}
                    {new Date(alert.last_triggered_at).toLocaleString("ko-KR")}
                  </span>
                )}
              </div>
            )}

            {/* ── 버튼 ── */}
            <div className="flex gap-3 pt-1">
              <button
                onClick={() => upsertMut.mutate()}
                disabled={isPending}
                aria-busy={upsertMut.isPending}
                className="flex-1 flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {upsertMut.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Bell size={14} />
                )}
                {hasAlert ? "설정 업데이트" : "자동화 설정"}
              </button>
              {hasAlert && (
                <button
                  onClick={() => deleteMut.mutate()}
                  disabled={isPending}
                  className="flex items-center justify-center gap-1.5 px-4 py-2 text-sm border border-red-300 text-red-600 rounded-lg hover:bg-red-50 dark:hover:bg-red-950 disabled:opacity-50 transition-colors"
                >
                  {deleteMut.isPending ? (
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
