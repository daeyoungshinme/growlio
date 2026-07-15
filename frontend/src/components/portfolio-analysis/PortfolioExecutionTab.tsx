import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchPortfolios } from "@/api/portfolios";
import { fetchAccounts } from "@/api/assets";
import { fetchRebalancingAlerts } from "@/api/alerts";
import { AnalysisPanel } from "./AnalysisPanel";
import RebalancingAlertModalRouter from "@/components/rebalancing/RebalancingAlertModalRouter";
import ErrorBoundary from "@/components/ErrorBoundary";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { mergeAlertsByPortfolio } from "@/utils/portfolio";

interface Props {
  portfolioId?: string;
}

export default function PortfolioExecutionTab({ portfolioId }: Props) {
  const [alertModalPortfolioId, setAlertModalPortfolioId] = useState<string | null>(null);

  // 추천 비중 카드의 "목표 포트폴리오에 적용" CTA 또는 푸시 알림 딥링크에서 넘어온 경우 실행 모달을 자동으로 연다.
  const [searchParams, setSearchParams] = useSearchParams();
  const [autoOpenExecution] = useState(() => searchParams.get("openExecution") === "1");

  useEffect(() => {
    if (searchParams.get("openExecution") !== "1") return;
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("openExecution");
        return next;
      },
      { replace: true },
    );
  }, [searchParams, setSearchParams]);

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
    return mergeAlertsByPortfolio(alerts);
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
          autoOpenExecution={autoOpenExecution}
        />
      </ErrorBoundary>

      {alertModalPortfolioId &&
        (() => {
          const alertPortfolio = portfolios.find((p) => p.id === alertModalPortfolioId);
          return (
            <RebalancingAlertModalRouter
              key={alertModalPortfolioId}
              portfolioId={alertModalPortfolioId}
              portfolioName={alertPortfolio?.name ?? ""}
              alertScope={alertPortfolio?.alert_scope}
              accountIds={alertPortfolio?.account_ids ?? null}
              accounts={accounts}
              onClose={() => setAlertModalPortfolioId(null)}
            />
          );
        })()}
    </div>
  );
}
