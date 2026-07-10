import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellOff, Loader2 } from "lucide-react";
import Modal from "@/components/common/Modal";
import RebalancingAlertModal from "@/components/rebalancing/RebalancingAlertModal";
import {
  fetchAccountRebalancingAlerts,
  updateAlertScope,
  type RebalancingAlert,
} from "@/api/alerts";
import type { AssetAccount } from "@/api/assets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { STRATEGY_OPTIONS } from "@/constants/rebalancingConfig";
import { invalidatePortfolioData, invalidateRebalancingAlertData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";
import { relativeTime } from "@/utils/format";
import { buildAlertDescription } from "@/utils/rebalancingAlertDescription";

const ORDER_TYPE_LABEL: Record<RebalancingAlert["order_type"], string> = {
  MARKET: "시장가",
  LIMIT: "지정가",
};

function strategyLabel(strategy: RebalancingAlert["strategy"]): string {
  return STRATEGY_OPTIONS.find((s) => s.value === strategy)?.label ?? strategy;
}

interface Props {
  portfolioId: string;
  portfolioName: string;
  linkedAccounts: AssetAccount[];
  onClose: () => void;
}

export default function PerAccountRebalancingAlertList({
  portfolioId,
  portfolioName,
  linkedAccounts,
  onClose,
}: Props) {
  const qc = useQueryClient();
  const [editingAccount, setEditingAccount] = useState<AssetAccount | null>(null);
  const [confirmingSwitchBack, setConfirmingSwitchBack] = useState(false);

  const { data: alertsRaw, isLoading } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlertsByAccount(portfolioId),
    queryFn: () => fetchAccountRebalancingAlerts(portfolioId),
    staleTime: STALE_TIME.MEDIUM,
  });
  const alerts = Array.isArray(alertsRaw) ? alertsRaw : [];
  const alertByAccountId: Record<string, RebalancingAlert> = Object.fromEntries(
    alerts.map((a) => [a.account_id, a]),
  );

  const switchToAggregateMut = useMutation({
    mutationFn: () => updateAlertScope(portfolioId, "AGGREGATE"),
    onSuccess: () => {
      void invalidatePortfolioData(qc);
      void invalidateRebalancingAlertData(qc, portfolioId);
      toast("전체 통합 설정으로 전환되었습니다", "success");
      onClose();
    },
    onError: (e) => toast(extractErrorMessage(e, "전환에 실패했습니다"), "error"),
  });

  function handleSwitchBackClick() {
    if (!confirmingSwitchBack) {
      setConfirmingSwitchBack(true);
      setTimeout(() => setConfirmingSwitchBack(false), 3000);
    } else {
      switchToAggregateMut.mutate();
    }
  }

  return (
    <>
      <Modal
        title={`계좌별 리밸런싱 자동화 — ${portfolioName}`}
        onClose={onClose}
        size="md"
        closeOnBackdrop
      >
        <div className="flex-1 overflow-y-auto overscroll-contain p-4 space-y-3">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            이 포트폴리오에 연결된 계좌마다 알림/자동매매를 독립적으로 설정합니다.
          </p>
          {isLoading ? (
            <div className="flex justify-center py-4">
              <Loader2 size={20} className="animate-spin text-gray-400" />
            </div>
          ) : (
            <ul className="space-y-2">
              {linkedAccounts.map((account) => {
                const alert = alertByAccountId[account.id];
                return (
                  <li
                    key={account.id}
                    className="flex items-start justify-between gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                        {account.name}
                      </p>
                      {alert ? (
                        <>
                          <p className="text-xs text-gray-400 dark:text-gray-500">
                            {buildAlertDescription(
                              alert.schedule_type,
                              alert.schedule_day_of_week ?? 0,
                              alert.schedule_day_of_month ?? 1,
                              alert.trigger_condition,
                              alert.threshold_pct,
                              alert.mode,
                              alert.auto_execution_time ?? undefined,
                              alert.notify_time,
                            )}
                          </p>
                          {alert.mode === "AUTO" && (
                            <p className="text-xs text-orange-500 dark:text-orange-400">
                              {strategyLabel(alert.strategy)} · {ORDER_TYPE_LABEL[alert.order_type]}
                            </p>
                          )}
                          {alert.last_triggered_at && (
                            <p className="text-xs text-gray-400 dark:text-gray-500">
                              마지막 실행: {relativeTime(alert.last_triggered_at)}
                            </p>
                          )}
                        </>
                      ) : (
                        <p className="text-xs text-gray-400 dark:text-gray-500">미설정</p>
                      )}
                    </div>
                    <button
                      onClick={() => setEditingAccount(account)}
                      className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                    >
                      {alert ? <Bell size={12} /> : <BellOff size={12} />}
                      {alert ? "설정 편집" : "설정하기"}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <div className="sticky bottom-0 bg-white dark:bg-gray-900 px-4 py-3 border-t border-gray-100 dark:border-gray-700">
          <button
            onClick={handleSwitchBackClick}
            disabled={switchToAggregateMut.isPending}
            className={`w-full flex items-center justify-center gap-2 py-2 text-sm rounded-lg disabled:opacity-50 transition-colors ${
              confirmingSwitchBack
                ? "bg-gray-600 text-white hover:bg-gray-700"
                : "border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800"
            }`}
          >
            {switchToAggregateMut.isPending && <Loader2 size={14} className="animate-spin" />}
            {confirmingSwitchBack
              ? "정말 전환? (계좌별 설정 모두 삭제됨)"
              : "전체 통합 설정으로 전환"}
          </button>
        </div>
      </Modal>

      {editingAccount && (
        <RebalancingAlertModal
          key={editingAccount.id}
          portfolioId={portfolioId}
          portfolioName={portfolioName}
          targetAccountId={editingAccount.id}
          targetAccountName={editingAccount.name}
          onClose={() => setEditingAccount(null)}
        />
      )}
    </>
  );
}
