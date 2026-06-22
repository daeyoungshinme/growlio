import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bell, BellOff, Plus, Zap } from "lucide-react";
import { fetchPortfolios } from "@/api/portfolios";
import { fetchRebalancingAlerts } from "@/api/alerts";
import RebalancingAlertModal from "./RebalancingAlertModal";
import EmptyState from "@/components/common/EmptyState";
import SkeletonCard from "@/components/common/SkeletonCard";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { SCHEDULE_LABEL } from "@/constants/rebalancingConfig";
import { relativeTime } from "@/utils/format";

export default function RebalancingAlertListTab() {
  const [alertModalPortfolioId, setAlertModalPortfolioId] = useState<string | null>(null);

  const { data: portfoliosRaw, isLoading: portfoliosLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
  });
  const portfolios = useMemo(
    () => (Array.isArray(portfoliosRaw) ? portfoliosRaw : []),
    [portfoliosRaw],
  );

  const { data: alertsRaw, isLoading: alertsLoading } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlerts,
    queryFn: fetchRebalancingAlerts,
    staleTime: STALE_TIME.MEDIUM,
  });
  const alertByPortfolioId = useMemo(() => {
    const alerts = Array.isArray(alertsRaw) ? alertsRaw : [];
    return Object.fromEntries(alerts.map((a) => [a.portfolio_id, a]));
  }, [alertsRaw]);

  const isLoading = portfoliosLoading || alertsLoading;

  if (isLoading) return <SkeletonCard rows={4} />;

  if (portfolios.length === 0) {
    return (
      <EmptyState
        title="포트폴리오가 없습니다."
        description="리밸런싱 자동화를 설정하려면 먼저 포트폴리오를 만드세요."
      />
    );
  }

  const alertedCount = portfolios.filter((p) => alertByPortfolioId[p.id]).length;

  return (
    <div className="space-y-4">
      {/* 요약 배너 */}
      <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800">
        <Bell size={16} className="text-blue-600 dark:text-blue-400 shrink-0" />
        <p className="text-sm text-blue-700 dark:text-blue-300">
          {alertedCount > 0
            ? `${portfolios.length}개 포트폴리오 중 ${alertedCount}개에 자동화가 설정되어 있습니다.`
            : "아직 자동화가 설정된 포트폴리오가 없습니다. 각 포트폴리오에 비중 이탈 알림 또는 자동 실행을 설정하세요."}
        </p>
      </div>

      {/* 포트폴리오 카드 목록 */}
      <div className="space-y-3">
        {portfolios.map((portfolio) => {
          const alert = alertByPortfolioId[portfolio.id];
          const hasAlert = !!alert;
          const isAuto = alert?.mode === "AUTO";

          return (
            <div
              key={portfolio.id}
              className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-gray-900 dark:text-gray-50 truncate">
                      {portfolio.name}
                    </span>
                    {hasAlert && (
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                          isAuto
                            ? "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300"
                            : "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300"
                        }`}
                      >
                        {isAuto ? <Zap size={10} /> : <Bell size={10} />}
                        {isAuto ? "자동 실행" : "알림만"}
                      </span>
                    )}
                    {!hasAlert && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                        <BellOff size={10} />
                        미설정
                      </span>
                    )}
                  </div>

                  {hasAlert && (
                    <div className="mt-1.5 space-y-1.5">
                      <div className="flex flex-wrap gap-1.5">
                        <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded-full text-xs">
                          {SCHEDULE_LABEL[alert.schedule_type]}
                        </span>
                        {alert.threshold_pct > 0 && (
                          <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded-full text-xs">
                            ±{alert.threshold_pct}% 이탈
                          </span>
                        )}
                        {alert.deposit_trigger_enabled && (
                          <span className="px-2 py-0.5 bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400 rounded-full text-xs">
                            입금 감지
                          </span>
                        )}
                      </div>
                      {alert.last_triggered_at && (
                        <p className="text-xs text-gray-400 dark:text-gray-500">
                          최근 실행: {relativeTime(alert.last_triggered_at)}
                        </p>
                      )}
                    </div>
                  )}
                  {!hasAlert && (
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      비중 이탈 시 알림 또는 자동 매수/매도를 설정하세요
                    </p>
                  )}
                </div>

                <button
                  onClick={() => setAlertModalPortfolioId(portfolio.id)}
                  className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    hasAlert
                      ? "border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800"
                      : "bg-blue-600 text-white hover:bg-blue-700"
                  }`}
                >
                  {hasAlert ? (
                    "설정 변경"
                  ) : (
                    <>
                      <Plus size={12} />
                      자동화 설정
                    </>
                  )}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {alertModalPortfolioId && (
        <RebalancingAlertModal
          key={alertModalPortfolioId}
          portfolioId={alertModalPortfolioId}
          portfolioName={portfolios.find((p) => p.id === alertModalPortfolioId)?.name ?? ""}
          accountIds={
            portfolios.find((p) => p.id === alertModalPortfolioId)?.account_ids ?? null
          }
          onClose={() => setAlertModalPortfolioId(null)}
        />
      )}
    </div>
  );
}
