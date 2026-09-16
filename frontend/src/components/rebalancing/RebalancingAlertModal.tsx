import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Modal from "@/components/common/Modal";
import { updateAlertScope } from "@/api/alerts";
import {
  useRebalancingAlertQueries,
  useRebalancingAlertFormState,
} from "@/hooks/useRebalancingAlertForm";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { invalidatePortfolioData } from "@/utils/queryInvalidation";
import { DCA_AUTO_BUY_THRESHOLD_PCT } from "@/constants/rebalancingConfig";
import { isDcaAutoBuyPreset } from "@/utils/dcaAutoBuy";
import { AlertScheduleSection } from "@/components/rebalancing/alertModal/AlertScheduleSection";
import { AlertTriggerSection } from "@/components/rebalancing/alertModal/AlertTriggerSection";
import { AlertModeSection } from "@/components/rebalancing/alertModal/AlertModeSection";
import { AlertAutoModeSection } from "@/components/rebalancing/alertModal/AlertAutoModeSection";
import { AlertQuickDcaSection } from "@/components/rebalancing/alertModal/AlertQuickDcaSection";
import { AlertSummarySection } from "@/components/rebalancing/alertModal/AlertSummarySection";
import { AlertActionsSection } from "@/components/rebalancing/alertModal/AlertActionsSection";

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
  const {
    alert,
    isLoading,
    autoExecutionAccounts,
    targetAccountIsAutoEligible,
    targetAccountTaxType,
    targetAccountInvestmentHorizon,
    marketSignal,
  } = useRebalancingAlertQueries({
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
            autoExecutionAccounts={autoExecutionAccounts}
            targetAccountIsAutoEligible={targetAccountIsAutoEligible}
            portfolioId={portfolioId}
            targetAccountId={targetAccountId}
            targetAccountName={targetAccountName}
            targetAccountTaxType={targetAccountTaxType}
            targetAccountInvestmentHorizon={targetAccountInvestmentHorizon}
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
import type { AccountTaxType, AssetAccount, InvestmentHorizon } from "@/api/assets";
import type { MarketSignalResponse } from "@/api/marketSignals";

function AlertFormBody({
  alert,
  autoExecutionAccounts,
  targetAccountIsAutoEligible,
  portfolioId,
  targetAccountId,
  targetAccountName,
  targetAccountTaxType,
  targetAccountInvestmentHorizon,
  canSwitchToPerAccount,
  onSwitchToPerAccount,
  onClose,
  marketSignal,
}: {
  alert: RebalancingAlert | null;
  autoExecutionAccounts: AssetAccount[];
  targetAccountIsAutoEligible: boolean;
  portfolioId: string;
  targetAccountId?: string;
  targetAccountName?: string;
  targetAccountTaxType?: AccountTaxType;
  targetAccountInvestmentHorizon?: InvestmentHorizon | null;
  canSwitchToPerAccount?: boolean;
  onSwitchToPerAccount?: () => void;
  onClose: () => void;
  marketSignal?: MarketSignalResponse;
}) {
  const form = useRebalancingAlertFormState({
    alert,
    portfolioId,
    targetAccountId,
    targetAccountTaxType,
    targetAccountInvestmentHorizon,
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
    if (autoExecutionAccounts.length !== 1) return;
    setAccountId(autoExecutionAccounts[0].id);
  }, [mode, setAccountId, autoExecutionAccounts, targetAccountId]);

  const hasAlert = !!alert;
  const queryClient = useQueryClient();

  const switchToPerAccountMut = useMutation({
    mutationFn: () => updateAlertScope(portfolioId, "PER_ACCOUNT"),
    onSuccess: () => {
      void invalidatePortfolioData(queryClient);
      toast("계좌별 독립 설정으로 전환되었습니다", "success");
      onSwitchToPerAccount?.();
    },
    onError: (e) => toast(extractErrorMessage(e, "전환에 실패했습니다"), "error"),
  });

  // 신규 알림을 AGGREGATE 스코프로 만드는 경우에만 "빠른 설정" 선택지를 먼저 보여준다 —
  // 기존 알림 편집·PER_ACCOUNT 계좌별 설정(targetAccountId 지정)은 바로 상세 화면으로 간다.
  const canQuickSetup = !hasAlert && !targetAccountId;
  const [setupMode, setSetupMode] = useState<"choose" | "quick" | "advanced">(
    canQuickSetup ? "choose" : "advanced",
  );

  function applyDcaAutoBuyPreset() {
    form.setScheduleType("MONTHLY");
    form.setTriggerCondition("SCHEDULE_ONLY");
    form.setMode("AUTO");
    form.setStrategy("BUY_ONLY");
    form.setThreshold(DCA_AUTO_BUY_THRESHOLD_PCT);
    setSetupMode("quick");
  }

  if (setupMode === "choose") {
    return (
      <div className="p-4 space-y-3">
        <button
          type="button"
          onClick={applyDcaAutoBuyPreset}
          className="w-full text-left p-4 rounded-xl border-2 border-blue-500 bg-blue-50 dark:bg-blue-950 hover:bg-blue-100 dark:hover:bg-blue-900 transition-colors"
        >
          <div className="text-sm font-semibold text-blue-700 dark:text-blue-300">
            정기 적립식 자동매수로 빠르게 설정
          </div>
          <div className="text-xs text-blue-600 dark:text-blue-400 mt-1">
            매달 지정한 날짜에 계좌 예수금을 목표 비중대로 자동으로 나눠 매수합니다
          </div>
        </button>
        <button
          type="button"
          onClick={() => setSetupMode("advanced")}
          className="w-full text-left p-4 rounded-xl border border-gray-300 dark:border-gray-600 hover:border-gray-400 transition-colors"
        >
          <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
            직접 설정할래요 (고급)
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            드리프트 임계값·매도 포함 리밸런싱·알림만 받기 등을 직접 조합합니다
          </div>
        </button>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4 pb-2">
      {hasAlert && isDcaAutoBuyPreset(alert) && (
        <div className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-full px-2.5 py-1">
          정기 적립식 자동매수로 설정됨
        </div>
      )}
      {setupMode === "quick" ? (
        <AlertQuickDcaSection
          form={form}
          autoExecutionAccounts={autoExecutionAccounts}
          onSwitchToAdvanced={() => setSetupMode("advanced")}
        />
      ) : (
        <>
          <AlertScheduleSection form={form} />
          <AlertTriggerSection form={form} />
          <AlertModeSection
            form={form}
            targetAccountId={targetAccountId}
            targetAccountIsAutoEligible={targetAccountIsAutoEligible}
            autoExecutionAccounts={autoExecutionAccounts}
          />
          {form.mode === "AUTO" && (
            <AlertAutoModeSection
              form={form}
              targetAccountId={targetAccountId}
              targetAccountName={targetAccountName}
              autoExecutionAccounts={autoExecutionAccounts}
              canSwitchToPerAccount={canSwitchToPerAccount}
              switchToPerAccountMut={switchToPerAccountMut}
              marketSignal={marketSignal}
            />
          )}
        </>
      )}
      <AlertSummarySection form={form} alert={alert} />
      <AlertActionsSection
        form={form}
        hasAlert={hasAlert}
        portfolioId={portfolioId}
        targetAccountId={targetAccountId}
      />
    </div>
  );
}
