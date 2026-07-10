import RebalancingAlertModal from "@/components/rebalancing/RebalancingAlertModal";
import PerAccountRebalancingAlertList from "@/components/portfolio-analysis/PerAccountRebalancingAlertList";
import { isStockAccount } from "@/utils/accounts";
import type { AssetAccount } from "@/api/assets";

interface Props {
  portfolioId: string;
  portfolioName: string;
  alertScope?: "AGGREGATE" | "PER_ACCOUNT";
  accountIds: string[] | null;
  accounts: AssetAccount[];
  onClose: () => void;
}

/** 포트폴리오의 alert_scope에 따라 PER_ACCOUNT 목록/AGGREGATE 모달 중 올바른 화면으로 라우팅한다.
 * PER_ACCOUNT 포트폴리오에 AGGREGATE 전용 엔드포인트로 잘못 요청을 보내 409가 나는 것을 방지하기 위한
 * 공용 진입점 — 이 컴포넌트를 거치지 않고 RebalancingAlertModal을 직접 여는 곳을 새로 만들지 말 것. */
export default function RebalancingAlertModalRouter({
  portfolioId,
  portfolioName,
  alertScope,
  accountIds,
  accounts,
  onClose,
}: Props) {
  if (alertScope === "PER_ACCOUNT") {
    const linkedAccounts = accountIds
      ? accounts.filter(
          (a) => accountIds.includes(a.id) && a.is_active && isStockAccount(a.asset_type),
        )
      : [];
    return (
      <PerAccountRebalancingAlertList
        portfolioId={portfolioId}
        portfolioName={portfolioName}
        linkedAccounts={linkedAccounts}
        onClose={onClose}
      />
    );
  }

  return (
    <RebalancingAlertModal
      portfolioId={portfolioId}
      portfolioName={portfolioName}
      accountIds={accountIds}
      canSwitchToPerAccount={(accountIds?.length ?? 0) >= 2}
      onClose={onClose}
    />
  );
}
