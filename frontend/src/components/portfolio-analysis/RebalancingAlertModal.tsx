import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellOff, Loader2 } from "lucide-react";
import Modal from "../common/Modal";
import {
  fetchRebalancingAlert,
  upsertRebalancingAlert,
  deleteRebalancingAlert,
  type ScheduleType,
} from "../../api/alerts";
import { QUERY_KEYS } from "../../constants/queryKeys";
import { STALE_TIME } from "../../constants/queryConfig";
import { invalidateRebalancingAlertData } from "../../utils/queryInvalidation";
import { toast } from "../../utils/toast";
import { extractErrorMessage } from "../../utils/error";

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

  return onlyWhenDrift
    ? `비중이 ±${threshold.toFixed(1)}% 이상 이탈 시 ${when} 알림을 받습니다.`
    : `${when} 리밸런싱 현황 리포트를 받습니다.`;
}

const NEEDS_DAY_OF_MONTH: ScheduleType[] = ["MONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL"];

export default function RebalancingAlertModal({ portfolioId, portfolioName, onClose }: Props) {
  const qc = useQueryClient();

  const [scheduleType, setScheduleType] = useState<ScheduleType>("DAILY");
  const [dayOfWeek, setDayOfWeek] = useState(0);
  const [dayOfMonth, setDayOfMonth] = useState(1);
  const [onlyWhenDrift, setOnlyWhenDrift] = useState(true);
  const [threshold, setThreshold] = useState(5);

  const { data: alert, isLoading } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlert(portfolioId),
    queryFn: () => fetchRebalancingAlert(portfolioId),
    staleTime: STALE_TIME.MEDIUM,
    retry: (failureCount, error: unknown) => {
      const status = (error as { response?: { status?: number } })?.response?.status;
      return status === 404 ? false : failureCount < 2;
    },
  });

  useEffect(() => {
    if (!alert) return;
    setScheduleType(alert.schedule_type);
    setDayOfWeek(alert.schedule_day_of_week ?? 0);
    setDayOfMonth(alert.schedule_day_of_month ?? 1);
    setOnlyWhenDrift(alert.only_when_drift);
    setThreshold(alert.threshold_pct);
  }, [alert]);

  const upsertMut = useMutation({
    mutationFn: () =>
      upsertRebalancingAlert(portfolioId, {
        threshold_pct: threshold,
        schedule_type: scheduleType,
        schedule_day_of_week: scheduleType === "WEEKLY" ? dayOfWeek : null,
        schedule_day_of_month: NEEDS_DAY_OF_MONTH.includes(scheduleType) ? dayOfMonth : null,
        only_when_drift: onlyWhenDrift,
      }),
    onSuccess: () => {
      invalidateRebalancingAlertData(qc, portfolioId);
      toast("알림이 설정되었습니다", "success");
      onClose();
    },
    onError: (e) => toast(extractErrorMessage(e, "알림 설정에 실패했습니다")),
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteRebalancingAlert(portfolioId),
    onSuccess: () => {
      invalidateRebalancingAlertData(qc, portfolioId);
      toast("알림이 해제되었습니다", "success");
      onClose();
    },
    onError: (e) => toast(extractErrorMessage(e, "알림 해제에 실패했습니다")),
  });

  const isPending = upsertMut.isPending || deleteMut.isPending;
  const hasAlert = !!alert;

  return (
    <Modal title={`리밸런싱 알림 — ${portfolioName}`} onClose={onClose} size="sm" closeOnBackdrop>
      <div className="p-6 space-y-5">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Loader2 size={20} className="animate-spin text-gray-400" />
          </div>
        ) : (
          <>
            {/* ── 알림 주기 ── */}
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">알림 주기</p>
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
                    {SCHEDULE_LABEL[scheduleType]}마다 이 날짜에 발송
                  </span>
                </div>
              </div>
            )}

            {/* ── 알림 조건 ── */}
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">알림 조건</p>
              <div className="space-y-2">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="radio"
                    checked={onlyWhenDrift}
                    onChange={() => setOnlyWhenDrift(true)}
                    className="mt-0.5 text-blue-600"
                  />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    비중 이탈 시에만 발송
                    <span className="block text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                      이탈 종목이 있을 때만 알림을 보냅니다
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
                    주기마다 항상 발송
                    <span className="block text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                      이탈 여부와 관계없이 주기마다 전체 현황을 보냅니다
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

            {/* ── 설명 텍스트 ── */}
            <p className="text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2">
              {buildDescription(scheduleType, dayOfWeek, dayOfMonth, onlyWhenDrift, threshold)}
            </p>

            {/* ── 현재 설정 표시 ── */}
            {hasAlert && (
              <div className="rounded-lg bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 p-3 text-xs text-blue-700 dark:text-blue-300">
                현재 알림이 활성화되어 있습니다.
                {alert.last_triggered_at && (
                  <span className="block mt-0.5 text-blue-500">
                    마지막 발송:{" "}
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
                className="flex-1 flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {upsertMut.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Bell size={14} />
                )}
                {hasAlert ? "알림 업데이트" : "알림 설정"}
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
                  알림 해제
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
