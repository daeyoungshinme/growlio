import { Loader2 } from "lucide-react";
import { useEffect } from "react";
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
import { AlertScheduleSection } from "@/components/rebalancing/alertModal/AlertScheduleSection";
import { AlertTriggerSection } from "@/components/rebalancing/alertModal/AlertTriggerSection";
import { AlertModeSection } from "@/components/rebalancing/alertModal/AlertModeSection";
import { AlertAutoModeSection } from "@/components/rebalancing/alertModal/AlertAutoModeSection";
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
    kisExecutionAccounts,
    targetAccountIsKis,
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
            kisExecutionAccounts={kisExecutionAccounts}
            targetAccountIsKis={targetAccountIsKis}
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
  kisExecutionAccounts,
  targetAccountIsKis,
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
  kisExecutionAccounts: AssetAccount[];
  targetAccountIsKis: boolean;
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
    if (kisExecutionAccounts.length !== 1) return;
    setAccountId(kisExecutionAccounts[0].id);
  }, [mode, setAccountId, kisExecutionAccounts, targetAccountId]);

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

  return (
    <div className="p-4 space-y-4 pb-2">
      <AlertScheduleSection form={form} />
      <AlertTriggerSection form={form} />
      <AlertModeSection
        form={form}
        targetAccountId={targetAccountId}
        targetAccountIsKis={targetAccountIsKis}
        kisExecutionAccounts={kisExecutionAccounts}
      />
      {form.mode === "AUTO" && (
        <AlertAutoModeSection
          form={form}
          targetAccountId={targetAccountId}
          targetAccountName={targetAccountName}
          kisExecutionAccounts={kisExecutionAccounts}
          canSwitchToPerAccount={canSwitchToPerAccount}
          switchToPerAccountMut={switchToPerAccountMut}
          marketSignal={marketSignal}
        />
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
