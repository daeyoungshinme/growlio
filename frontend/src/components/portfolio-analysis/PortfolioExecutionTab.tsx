import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchAccounts } from "@/api/assets";
import { fetchRebalancingAlerts } from "@/api/alerts";
import { AnalysisPanel } from "./AnalysisPanel";
import ErrorBoundary from "@/components/ErrorBoundary";
import EmptyState from "@/components/common/EmptyState";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { mergeAlertsByPortfolio } from "@/utils/portfolio";
import { portfoliosQuery } from "@/api/queryOptions";

interface Props {
  /** 분석 대상 — 페이지가 URL 선택값 또는 기본 포트폴리오(useSelectedPortfolio)로 정해 넘긴다 */
  portfolioId: string;
  /** false면 분석 결과로 자동 스크롤하지 않는다 — 기본 선택(URL 미지정)으로 열린 경우 */
  scrollToResult?: boolean;
}

export default function PortfolioExecutionTab({ portfolioId, scrollToResult }: Props) {
  // 푸시 알림 딥링크에서 넘어온 경우 실행 모달을 자동으로 연다.
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

  const {
    data: portfoliosRaw,
    isLoading: portfoliosLoading,
    isError: portfoliosError,
    refetch: refetchPortfolios,
  } = useQuery(portfoliosQuery);
  const portfolios = useMemo(
    () => (Array.isArray(portfoliosRaw) ? portfoliosRaw : []),
    [portfoliosRaw],
  );

  const { data: accountsRaw, isLoading: accountsLoading } = useQuery({
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

  // 모달은 PortfolioManageTab이 단일 호스트로 띄운다 — 여기선 URL 파라미터로 요청만 보낸다(U8).
  const openAlertModal = (id: string) =>
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("portfolioId", id);
        next.set("openAlert", "1");
        return next;
      },
      { replace: true },
    );

  if (portfoliosLoading) {
    return <div className="h-32 bg-gray-100 dark:bg-gray-800 rounded-xl animate-pulse" />;
  }

  if (portfoliosError) {
    return (
      <EmptyState
        title="포트폴리오를 불러오지 못했습니다."
        action={{ label: "다시 시도", onClick: () => void refetchPortfolios() }}
      />
    );
  }

  // 방금 삭제된 포트폴리오 등 — 목록에 없으면 그리지 않는다(빈 상태는 위 목록이 담당)
  if (!portfolios.some((p) => p.id === portfolioId)) return null;

  return (
    <div className="space-y-4">
      <ErrorBoundary variant="section">
        <AnalysisPanel
          portfolioId={portfolioId}
          portfolios={portfolios}
          activeAccounts={activeAccounts}
          onOpenAlertModal={openAlertModal}
          alertByPortfolioId={alertByPortfolioId}
          autoOpenExecution={autoOpenExecution}
          accountsReady={!accountsLoading}
          scrollToResult={scrollToResult}
        />
      </ErrorBoundary>
    </div>
  );
}
