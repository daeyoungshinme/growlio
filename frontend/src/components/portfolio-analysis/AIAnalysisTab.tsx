import { AlertTriangle, RefreshCw, Sparkles } from "lucide-react";
import { useAIAnalysis } from "@/hooks/useAIAnalysis";
import MarketOverviewCard from "./MarketOverviewCard";
import AIRiskDiagnosisCard from "./AIRiskDiagnosisCard";
import RecommendationList from "./RecommendationList";
import AlternativePortfolioCard from "./AlternativePortfolioCard";

function Skeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-48 bg-gray-100 dark:bg-gray-800 rounded-2xl" />
      <div className="h-6 w-48 bg-gray-100 dark:bg-gray-800 rounded-xl" />
      <div className="h-32 bg-gray-100 dark:bg-gray-800 rounded-2xl" />
      <div className="h-40 bg-gray-100 dark:bg-gray-800 rounded-2xl" />
    </div>
  );
}

export default function AIAnalysisTab() {
  const { data, isLoading, refresh, refreshing } = useAIAnalysis();

  if (isLoading) return <Skeleton />;

  if (data?.status === "error") {
    const isRateLimit = data.error_message?.includes("한도를 초과");
    return (
      <div className="flex flex-col gap-3 p-4 rounded-xl bg-red-50 dark:bg-red-950 text-red-600 dark:text-red-400">
        <div className="flex items-start gap-2">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" />
          <div className="flex flex-col gap-1">
            <span className="text-sm">{data.error_message ?? "분석 중 오류가 발생했습니다."}</span>
            {isRateLimit && (
              <span className="text-xs text-red-400 dark:text-red-500">약 5분 후 재시도하면 새 분석을 받을 수 있습니다.</span>
            )}
          </div>
        </div>
        <button
          onClick={() => refresh()}
          disabled={refreshing}
          className="self-start flex items-center gap-1.5 px-3 py-1.5 text-xs border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-100 dark:hover:bg-red-900 disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={11} className={refreshing ? "animate-spin" : ""} />
          {refreshing ? "분석 중..." : "다시 시도"}
        </button>
      </div>
    );
  }

  const cachedAt = data?.cached_at ? new Date(data.cached_at) : null;

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Sparkles size={15} className="text-blue-500 shrink-0" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">AI 포트폴리오 분석</span>
          {cachedAt && (
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {cachedAt.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })} 기준
            </span>
          )}
        </div>
        <button
          onClick={() => refresh()}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-950 disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
          {refreshing ? "분석 중..." : "새로 분석"}
        </button>
      </div>

      {/* 시장 현황 */}
      <MarketOverviewCard
        indices={data?.market_indices ?? []}
        exchangeRate={data?.exchange_rate}
        sectors={data?.sector_performance ?? []}
      />

      {data?.analysis && (
        <>
          {/* 시황 요약 */}
          <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-4">
            <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
              {data.analysis.market_summary}
            </p>
          </div>

          {/* 리스크 진단 */}
          <AIRiskDiagnosisCard risk={data.analysis.portfolio_risk} />

          {/* 추천 액션 */}
          <RecommendationList recommendations={data.analysis.recommendations} />

          {/* 대안 포트폴리오 */}
          {data.analysis.alternative_portfolios.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-semibold text-gray-700 dark:text-gray-300">대안 포트폴리오</p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {data.analysis.alternative_portfolios.map((portfolio) => (
                  <AlternativePortfolioCard key={portfolio.risk_level} portfolio={portfolio} />
                ))}
              </div>
            </div>
          )}

          {/* 면책 고지 */}
          <p className="text-xs text-gray-400 dark:text-gray-500 p-3 rounded-xl bg-gray-50 dark:bg-gray-800 leading-relaxed">
            {data.analysis.disclaimer}
          </p>
        </>
      )}
    </div>
  );
}
