import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteAccountRebalancingAlert,
  deleteRebalancingAlert,
  fetchAccountRebalancingAlert,
  fetchRebalancingAlert,
  upsertAccountRebalancingAlert,
  upsertRebalancingAlert,
  type MarketConditionMode,
  type RebalancingAlert,
  type ScheduleType,
  type TriggerCondition,
} from "@/api/alerts";
import { fetchAccounts } from "@/api/assets";
import { fetchMarketSignal } from "@/api/marketSignals";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateRebalancingAlertData } from "@/utils/queryInvalidation";
import { extractErrorMessage, getHttpStatus } from "@/utils/error";
import { toast } from "@/utils/toast";

const NEEDS_DAY_OF_MONTH: ScheduleType[] = ["MONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL"];

interface UseRebalancingAlertFormOpts {
  portfolioId: string;
  accountIds?: string[] | null;
  /** 지정 시 이 계좌 전용 알림(PER_ACCOUNT 스코프)을 조회/저장한다 (실행계좌 선택과는 별개 개념). */
  targetAccountId?: string;
}

export function useRebalancingAlertQueries({
  portfolioId,
  accountIds,
  targetAccountId,
}: UseRebalancingAlertFormOpts) {
  const { data: alert, isLoading } = useQuery({
    queryKey: targetAccountId
      ? QUERY_KEYS.rebalancingAlertByAccount(portfolioId, targetAccountId)
      : QUERY_KEYS.rebalancingAlert(portfolioId),
    queryFn: () =>
      targetAccountId
        ? fetchAccountRebalancingAlert(portfolioId, targetAccountId)
        : fetchRebalancingAlert(portfolioId),
    staleTime: STALE_TIME.MEDIUM,
    retry: (failureCount, error: unknown) => {
      const status = getHttpStatus(error);
      return status === 404 ? false : failureCount < 2;
    },
  });

  const { data: accounts = [], isLoading: accountsLoading } = useQuery({
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

  const kisAccounts = brokerAccounts.filter(
    (a) => a.asset_type === "STOCK_KIS" && (accountIds == null || accountIds.includes(a.id)),
  );

  const kisExecutionAccounts = accounts.filter(
    (a) =>
      a.asset_type === "STOCK_KIS" &&
      a.is_active &&
      (accountIds == null || accountIds.includes(a.id)),
  );

  const targetAccountIsKis = targetAccountId
    ? accounts.find((a) => a.id === targetAccountId)?.asset_type === "STOCK_KIS"
    : true;

  return {
    alert: alert ?? null,
    isLoading: isLoading || (targetAccountId ? accountsLoading : false),
    brokerAccounts,
    kisAccounts,
    kisExecutionAccounts,
    targetAccountIsKis,
    marketSignal,
  };
}

interface UseRebalancingAlertFormStateOpts {
  alert: RebalancingAlert | null;
  portfolioId: string;
  /** 지정 시 계좌별 독립 설정(PER_ACCOUNT) API로 저장/삭제한다. */
  targetAccountId?: string;
  onClose: () => void;
}

export function useRebalancingAlertFormState({
  alert,
  portfolioId,
  targetAccountId,
  onClose,
}: UseRebalancingAlertFormStateOpts) {
  const qc = useQueryClient();

  const [scheduleType, setScheduleType] = useState<ScheduleType>(alert?.schedule_type ?? "DAILY");
  const [dayOfWeek, setDayOfWeek] = useState(alert?.schedule_day_of_week ?? 0);
  const [dayOfMonth, setDayOfMonth] = useState(alert?.schedule_day_of_month ?? 1);
  const [triggerCondition, setTriggerCondition] = useState<TriggerCondition>(
    alert?.trigger_condition ?? "DRIFT_ONLY",
  );
  const [threshold, setThreshold] = useState(alert?.threshold_pct ?? 5);
  const [mode, setMode] = useState<"NOTIFY" | "AUTO">(alert?.mode ?? "NOTIFY");
  const [strategy, setStrategy] = useState<"FULL" | "BUY_ONLY" | "TWO_PHASE">(
    alert?.strategy ?? "BUY_ONLY",
  );
  const [accountId, setAccountId] = useState<string>(alert?.account_id ?? targetAccountId ?? "");
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT">(alert?.order_type ?? "MARKET");
  const [marketConditionMode, setMarketConditionMode] = useState<MarketConditionMode>(
    alert?.market_condition_mode ?? "DISABLED",
  );
  const [autoExecutionTime, setAutoExecutionTime] = useState<string>(
    alert?.auto_execution_time ?? "09:05",
  );
  const [notifyTime, setNotifyTime] = useState<string>(alert?.notify_time ?? "08:30");
  const [buyWaitMinutes, setBuyWaitMinutes] = useState<number>(alert?.buy_wait_minutes ?? 10);

  const upsertMut = useMutation({
    mutationFn: () => {
      const body = {
        threshold_pct: threshold,
        schedule_type: scheduleType,
        schedule_day_of_week: scheduleType === "WEEKLY" ? dayOfWeek : null,
        schedule_day_of_month: NEEDS_DAY_OF_MONTH.includes(scheduleType) ? dayOfMonth : null,
        trigger_condition: triggerCondition,
        mode,
        strategy,
        account_id: mode === "AUTO" && accountId ? accountId : null,
        order_type: orderType,
        market_condition_mode: mode === "AUTO" ? marketConditionMode : "DISABLED",
        auto_execution_time: mode === "AUTO" && autoExecutionTime ? autoExecutionTime : null,
        notify_time: notifyTime,
        buy_wait_minutes: buyWaitMinutes,
      };
      return targetAccountId
        ? upsertAccountRebalancingAlert(portfolioId, targetAccountId, body)
        : upsertRebalancingAlert(portfolioId, body);
    },
    onSuccess: () => {
      void invalidateRebalancingAlertData(qc, portfolioId);
      toast("설정이 저장되었습니다", "success");
      onClose();
    },
    onError: (e) => toast(extractErrorMessage(e, "설정 저장에 실패했습니다")),
  });

  const deleteMut = useMutation({
    mutationFn: () =>
      targetAccountId
        ? deleteAccountRebalancingAlert(portfolioId, targetAccountId)
        : deleteRebalancingAlert(portfolioId),
    onSuccess: () => {
      void invalidateRebalancingAlertData(qc, portfolioId);
      toast("설정이 해제되었습니다", "success");
      onClose();
    },
    onError: (e) => toast(extractErrorMessage(e, "설정 해제에 실패했습니다")),
  });

  return {
    // form state
    scheduleType,
    setScheduleType,
    dayOfWeek,
    setDayOfWeek,
    dayOfMonth,
    setDayOfMonth,
    triggerCondition,
    setTriggerCondition,
    threshold,
    setThreshold,
    mode,
    setMode,
    strategy,
    setStrategy,
    accountId,
    setAccountId,
    orderType,
    setOrderType,
    marketConditionMode,
    setMarketConditionMode,
    autoExecutionTime,
    setAutoExecutionTime,
    notifyTime,
    setNotifyTime,
    buyWaitMinutes,
    setBuyWaitMinutes,
    // mutations
    upsertMut,
    deleteMut,
    isPending: upsertMut.isPending || deleteMut.isPending,
  };
}
