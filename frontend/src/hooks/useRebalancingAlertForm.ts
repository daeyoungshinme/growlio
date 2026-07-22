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
  type TaxImpactGateMode,
  type TriggerCondition,
} from "@/api/alerts";
import { fetchAccounts, type AccountTaxType, type InvestmentHorizon } from "@/api/assets";
import { fetchMarketSignal } from "@/api/marketSignals";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateRebalancingAlertData } from "@/utils/queryInvalidation";
import { extractErrorMessage, getHttpStatus } from "@/utils/error";
import { toast } from "@/utils/toast";
import { recommendDriftThresholdPct } from "@/utils/rebalancingThresholdRecommendation";

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

  const executionEligibleAccounts = brokerAccounts.filter(
    (a) => accountIds == null || accountIds.includes(a.id),
  );

  const autoExecutionAccounts = accounts.filter(
    (a) =>
      (a.asset_type === "STOCK_KIS" || a.asset_type === "STOCK_KIWOOM") &&
      a.is_active &&
      (accountIds == null || accountIds.includes(a.id)),
  );

  const targetAccount = targetAccountId
    ? accounts.find((a) => a.id === targetAccountId)
    : undefined;
  const targetAccountIsAutoEligible = targetAccountId
    ? targetAccount?.asset_type === "STOCK_KIS" || targetAccount?.asset_type === "STOCK_KIWOOM"
    : true;

  return {
    alert: alert ?? null,
    isLoading: isLoading || (targetAccountId ? accountsLoading : false),
    brokerAccounts,
    executionEligibleAccounts,
    autoExecutionAccounts,
    targetAccountIsAutoEligible,
    targetAccountTaxType: targetAccount?.tax_type,
    targetAccountInvestmentHorizon: targetAccount?.investment_horizon,
    marketSignal,
  };
}

interface UseRebalancingAlertFormStateOpts {
  alert: RebalancingAlert | null;
  portfolioId: string;
  /** 지정 시 계좌별 독립 설정(PER_ACCOUNT) API로 저장/삭제한다. */
  targetAccountId?: string;
  /** 대상 계좌의 tax_type/investment_horizon — 신규 알림 생성 시 임계값 추천에 사용. */
  targetAccountTaxType?: AccountTaxType;
  targetAccountInvestmentHorizon?: InvestmentHorizon | null;
  onClose: () => void;
}

export function useRebalancingAlertFormState({
  alert,
  portfolioId,
  targetAccountId,
  targetAccountTaxType,
  targetAccountInvestmentHorizon,
  onClose,
}: UseRebalancingAlertFormStateOpts) {
  const qc = useQueryClient();

  // 계좌 유형 기반 추천값 — 신규 알림 생성 시에만 초기값으로 사용, 기존 알림은 저장된 값을 유지한다.
  const recommendedThreshold = recommendDriftThresholdPct(
    targetAccountTaxType,
    targetAccountInvestmentHorizon,
  );

  const [scheduleType, setScheduleType] = useState<ScheduleType>(alert?.schedule_type ?? "DAILY");
  const [dayOfWeek, setDayOfWeek] = useState(alert?.schedule_day_of_week ?? 0);
  const [dayOfMonth, setDayOfMonth] = useState(alert?.schedule_day_of_month ?? 1);
  const [triggerCondition, setTriggerCondition] = useState<TriggerCondition>(
    alert?.trigger_condition ?? "DRIFT_ONLY",
  );
  const [threshold, setThreshold] = useState(alert?.threshold_pct ?? recommendedThreshold);
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
  const [taxImpactGateMode, setTaxImpactGateMode] = useState<TaxImpactGateMode>(
    alert?.tax_impact_gate_mode ?? "DISABLED",
  );
  const [maxTaxImpactKrw, setMaxTaxImpactKrw] = useState<number | null>(
    alert?.max_tax_impact_krw ?? null,
  );

  const upsertMut = useMutation({
    mutationFn: () => {
      if (mode === "AUTO" && !accountId) {
        throw new Error("자동 실행 모드에는 실행 계좌를 선택해야 합니다");
      }
      if (
        mode === "AUTO" &&
        taxImpactGateMode === "ENABLED" &&
        !(maxTaxImpactKrw && maxTaxImpactKrw > 0)
      ) {
        throw new Error("세금영향 게이트를 켰다면 추정 양도세 상한을 입력해야 합니다");
      }

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
        tax_impact_gate_mode: mode === "AUTO" ? taxImpactGateMode : "DISABLED",
        max_tax_impact_krw:
          mode === "AUTO" && taxImpactGateMode === "ENABLED" ? maxTaxImpactKrw : null,
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
    recommendedThreshold,
    isNewAlert: !alert,
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
    taxImpactGateMode,
    setTaxImpactGateMode,
    maxTaxImpactKrw,
    setMaxTaxImpactKrw,
    // mutations
    upsertMut,
    deleteMut,
    isPending: upsertMut.isPending || deleteMut.isPending,
  };
}

/** 알림 모달의 각 섹션 컴포넌트(alertModal/)가 공유하는 폼 상태 타입. */
export type RebalancingAlertFormState = ReturnType<typeof useRebalancingAlertFormState>;
