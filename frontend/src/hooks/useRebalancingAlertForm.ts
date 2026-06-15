import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteRebalancingAlert,
  fetchRebalancingAlert,
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
}

export function useRebalancingAlertQueries({ portfolioId, accountIds }: UseRebalancingAlertFormOpts) {
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

  const kisAccounts = brokerAccounts.filter(
    (a) => a.asset_type === "STOCK_KIS" && (accountIds == null || accountIds.includes(a.id)),
  );

  return { alert: alert ?? null, isLoading, brokerAccounts, kisAccounts, marketSignal };
}

interface UseRebalancingAlertFormStateOpts {
  alert: RebalancingAlert | null;
  portfolioId: string;
  accountIds?: string[] | null;
  kisAccounts: ReturnType<typeof useRebalancingAlertQueries>["kisAccounts"];
  onClose: () => void;
}

export function useRebalancingAlertFormState({
  alert,
  portfolioId,
  accountIds: _accountIds,
  kisAccounts,
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
  const [strategy, setStrategy] = useState<"FULL" | "BUY_ONLY">(alert?.strategy ?? "BUY_ONLY");
  const [accountId, setAccountId] = useState<string>(alert?.account_id ?? "");
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT">(alert?.order_type ?? "MARKET");
  const [marketConditionMode, setMarketConditionMode] = useState<MarketConditionMode>(
    alert?.market_condition_mode ?? "DISABLED",
  );
  const [depositTriggerEnabled, setDepositTriggerEnabled] = useState(
    alert?.deposit_trigger_enabled ?? false,
  );
  const [depositTriggerAccountId, setDepositTriggerAccountId] = useState<string>(
    alert?.deposit_trigger_account_id ?? "",
  );
  const [depositTriggerMinAmount, setDepositTriggerMinAmount] = useState<number>(
    alert?.deposit_trigger_min_amount_krw ?? 100_000,
  );

  useEffect(() => {
    if (depositTriggerAccountId && kisAccounts.length > 0) {
      if (!kisAccounts.some((a) => a.id === depositTriggerAccountId)) {
        setDepositTriggerAccountId("");
      }
    }
  }, [kisAccounts, depositTriggerAccountId]);

  const upsertMut = useMutation({
    mutationFn: () =>
      upsertRebalancingAlert(portfolioId, {
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
        deposit_trigger_enabled: depositTriggerEnabled,
        deposit_trigger_account_id:
          depositTriggerEnabled && depositTriggerAccountId ? depositTriggerAccountId : null,
        deposit_trigger_min_amount_krw: depositTriggerEnabled ? depositTriggerMinAmount : null,
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

  return {
    // form state
    scheduleType, setScheduleType,
    dayOfWeek, setDayOfWeek,
    dayOfMonth, setDayOfMonth,
    triggerCondition, setTriggerCondition,
    threshold, setThreshold,
    mode, setMode,
    strategy, setStrategy,
    accountId, setAccountId,
    orderType, setOrderType,
    marketConditionMode, setMarketConditionMode,
    depositTriggerEnabled, setDepositTriggerEnabled,
    depositTriggerAccountId, setDepositTriggerAccountId,
    depositTriggerMinAmount, setDepositTriggerMinAmount,
    // mutations
    upsertMut,
    deleteMut,
    isPending: upsertMut.isPending || deleteMut.isPending,
  };
}
