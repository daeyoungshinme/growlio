import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchPortfolios } from "@/api/portfolios";
import { fetchAccounts } from "@/api/assets";
import { fetchRebalancingAlerts } from "@/api/alerts";
import { AnalysisPanel } from "./AnalysisPanel";
import RebalancingAlertModal from "@/components/rebalancing/RebalancingAlertModal";
import ErrorBoundary from "@/components/ErrorBoundary";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

interface Props {
  portfolioId?: string;
}

export default function PortfolioExecutionTab({ portfolioId }: Props) {
  const [alertModalPortfolioId, setAlertModalPortfolioId] = useState<string | null>(null);

  const { data: portfoliosRaw, isLoading: portfoliosLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
  });
  const portfolios = useMemo(
    () => (Array.isArray(portfoliosRaw) ? portfoliosRaw : []),
    [portfoliosRaw],
  );

  const { data: accountsRaw } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
  });
  const accounts = Array.isArray(accountsRaw) ? accountsRaw : [];
  const activeAccounts = accounts.filter((a) => a.is_active);

  const { data: rebalancingAlertsRaw } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlerts,
    queryFn: fetchRebalancingAlerts,
    staleTime: STALE_TIME.MEDIUM,
  });
  const alertByPortfolioId = useMemo(() => {
    const alerts = Array.isArray(rebalancingAlertsRaw) ? rebalancingAlertsRaw : [];
    return Object.fromEntries(alerts.map((a) => [a.portfolio_id, a]));
  }, [rebalancingAlertsRaw]);

  const selectedIds = useMemo(
    () => (portfolioId ? new Set([portfolioId]) : new Set<string>()),
    [portfolioId],
  );
  const selectedPortfolio = portfolios.find((p) => p.id === portfolioId);
  const selectedNames = selectedPortfolio?.name ?? "";

  if (portfoliosLoading) {
    return <div className="h-32 bg-gray-100 dark:bg-gray-800 rounded-xl animate-pulse" />;
  }

  if (portfolios.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <p className="text-sm text-gray-500 dark:text-gray-400">포트폴리오가 없습니다.</p>
        <p className="text-xs text-gray-400 dark:text-gray-500">위에서 포트폴리오를 만드세요.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ErrorBoundary variant="section">
        <AnalysisPanel
          selectedIds={selectedIds}
          selectedNames={selectedNames}
          portfolios={portfolios}
          activeAccounts={activeAccounts}
          onOpenAlertModal={setAlertModalPortfolioId}
          autoAnalyzeId={portfolioId}
          alertByPortfolioId={alertByPortfolioId}
        />
      </ErrorBoundary>

      {alertModalPortfolioId && (
        <RebalancingAlertModal
          key={alertModalPortfolioId}
          portfolioId={alertModalPortfolioId}
          portfolioName={portfolios.find((p) => p.id === alertModalPortfolioId)?.name ?? ""}
          accountIds={portfolios.find((p) => p.id === alertModalPortfolioId)?.account_ids ?? null}
          onClose={() => setAlertModalPortfolioId(null)}
        />
      )}
    </div>
  );
}
