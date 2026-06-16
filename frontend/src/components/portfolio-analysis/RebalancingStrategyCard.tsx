import { useQuery } from "@tanstack/react-query";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";
import { fetchRebalancingStrategy } from "@/api/risk";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

const FACTOR_LABELS: Record<string, string> = {
  value: "가치",
  growth: "성장",
  size: "소형주",
  momentum: "모멘텀",
};

const ACTION_COLORS: Record<string, string> = {
  "신규 편입": "text-red-500 bg-red-50 dark:bg-red-900/20",
  "전량 매도": "text-blue-500 bg-blue-50 dark:bg-blue-900/20",
  "비중 확대": "text-red-500 bg-red-50 dark:bg-red-900/20",
  "비중 축소": "text-blue-500 bg-blue-50 dark:bg-blue-900/20",
};

interface Props {
  portfolioId: string;
  portfolioName: string;
}

function DeltaIcon({ delta }: { delta: number }) {
  if (delta > 1) return <TrendingUp size={12} className="text-amber-500" />;
  if (delta < -1) return <TrendingDown size={12} className="text-blue-400" />;
  return <Minus size={12} className="text-gray-400" />;
}

export default function RebalancingStrategyCard({ portfolioId, portfolioName }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: QUERY_KEYS.rebalancingStrategy(portfolioId),
    queryFn: () => fetchRebalancingStrategy(portfolioId),
    staleTime: STALE_TIME.MEDIUM,
  });

  if (isLoading) {
    return (
      <div className="card space-y-4">
        <div className="h-4 w-48 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        <div className="grid grid-cols-2 gap-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-16 bg-gray-100 dark:bg-gray-700 rounded-xl animate-pulse" />
          ))}
        </div>
        <div className="h-32 bg-gray-100 dark:bg-gray-700 rounded-xl animate-pulse" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="card flex items-center justify-center h-32 text-xs text-gray-400 dark:text-gray-500">
        전략 데이터를 불러올 수 없습니다
      </div>
    );
  }

  const { factor_changes, frontier_changes, trade_recommendations, overall_direction, summary } = data;
  const hasFrontier =
    frontier_changes.current_risk != null && frontier_changes.target_risk != null;

  return (
    <div className="card space-y-5">
      {/* 헤더 */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">전략 분석</h3>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            현재 포트폴리오 → <span className="text-amber-600 dark:text-amber-400 font-medium">{portfolioName}</span>
          </p>
        </div>
        <span className="shrink-0 px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400">
          {overall_direction}
        </span>
      </div>

      {/* 팩터 변화 + 프론티어 변화 나란히 */}
      <div className={`grid gap-4 ${hasFrontier ? "grid-cols-2" : "grid-cols-1"}`}>
        {/* 팩터 변화 */}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">팩터 변화</p>
          <div className="space-y-1.5">
            {Object.entries(factor_changes).map(([key, fc]) => (
              <div key={key} className="flex items-center justify-between text-xs">
                <span className="text-gray-600 dark:text-gray-400 w-14">
                  {FACTOR_LABELS[key] ?? key}
                </span>
                <div className="flex items-center gap-1">
                  <span className="text-gray-400 dark:text-gray-500 w-8 text-right">
                    {fc.current.toFixed(0)}
                  </span>
                  <span className="text-gray-300 dark:text-gray-600">→</span>
                  <span className="font-medium text-gray-700 dark:text-gray-300 w-8 text-right">
                    {fc.target.toFixed(0)}
                  </span>
                  <span
                    className={`w-10 text-right font-semibold flex items-center justify-end gap-0.5 ${
                      fc.delta > 1
                        ? "text-amber-600 dark:text-amber-400"
                        : fc.delta < -1
                        ? "text-blue-500"
                        : "text-gray-400 dark:text-gray-500"
                    }`}
                  >
                    <DeltaIcon delta={fc.delta} />
                    {fc.delta > 0 ? "+" : ""}
                    {fc.delta.toFixed(1)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 리스크·수익 변화 */}
        {hasFrontier && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">리스크·수익 변화</p>
            <div className="space-y-2">
              <div className="rounded-lg bg-gray-50 dark:bg-gray-700/50 p-2.5 text-xs">
                <p className="text-gray-400 dark:text-gray-500 mb-0.5">변동성</p>
                <p className="font-semibold text-gray-700 dark:text-gray-300">
                  {frontier_changes.current_risk!.toFixed(2)}% → {frontier_changes.target_risk!.toFixed(2)}%
                </p>
                <p
                  className={`text-xs font-medium mt-0.5 ${
                    (frontier_changes.risk_change ?? 0) < 0 ? "text-red-500" : "text-blue-500"
                  }`}
                >
                  {(frontier_changes.risk_change ?? 0) < 0 ? "" : "+"}
                  {frontier_changes.risk_change?.toFixed(2)}%p
                </p>
              </div>
              <div className="rounded-lg bg-gray-50 dark:bg-gray-700/50 p-2.5 text-xs">
                <p className="text-gray-400 dark:text-gray-500 mb-0.5">기대수익</p>
                <p className="font-semibold text-gray-700 dark:text-gray-300">
                  {frontier_changes.current_return! >= 0 ? "+" : ""}
                  {frontier_changes.current_return!.toFixed(2)}% → {frontier_changes.target_return! >= 0 ? "+" : ""}
                  {frontier_changes.target_return!.toFixed(2)}%
                </p>
                <p
                  className={`text-xs font-medium mt-0.5 ${
                    (frontier_changes.return_change ?? 0) > 0 ? "text-red-500" : "text-blue-500"
                  }`}
                >
                  {(frontier_changes.return_change ?? 0) > 0 ? "+" : ""}
                  {frontier_changes.return_change?.toFixed(2)}%p
                </p>
              </div>
              {frontier_changes.sharpe_improvement != null && (
                <div className="rounded-lg bg-gray-50 dark:bg-gray-700/50 p-2.5 text-xs">
                  <p className="text-gray-400 dark:text-gray-500 mb-0.5">Sharpe 비율</p>
                  <p className={`font-semibold ${frontier_changes.sharpe_improvement ? "text-red-500" : "text-blue-500"}`}>
                    {frontier_changes.sharpe_improvement ? "✓ 개선" : "✗ 하락"}
                  </p>
                  {frontier_changes.current_sharpe != null && frontier_changes.target_sharpe != null && (
                    <p className="text-gray-400 dark:text-gray-500 mt-0.5">
                      {frontier_changes.current_sharpe.toFixed(2)} → {frontier_changes.target_sharpe.toFixed(2)}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 종목별 조정 방향 */}
      {trade_recommendations.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">
            종목별 조정 방향
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-100 dark:border-gray-700">
                  <th className="text-left py-1.5 pr-2 font-medium text-gray-400 dark:text-gray-500">종목</th>
                  <th className="text-center py-1.5 px-1 font-medium text-gray-400 dark:text-gray-500">방향</th>
                  <th className="text-right py-1.5 px-1 font-medium text-gray-400 dark:text-gray-500">현재</th>
                  <th className="text-right py-1.5 px-1 font-medium text-gray-400 dark:text-gray-500">목표</th>
                  <th className="text-left py-1.5 pl-2 font-medium text-gray-400 dark:text-gray-500 hidden sm:table-cell">사유</th>
                </tr>
              </thead>
              <tbody>
                {trade_recommendations.map((rec, i) => (
                  <tr key={i} className="border-b border-gray-50 dark:border-gray-800 last:border-0">
                    <td className="py-1.5 pr-2 text-gray-700 dark:text-gray-300">
                      <span className="font-medium">{rec.ticker}</span>
                      <span className="ml-1 text-gray-400 dark:text-gray-500 text-xs">{rec.name.slice(0, 8)}</span>
                    </td>
                    <td className="py-1.5 px-1 text-center">
                      <span
                        className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${
                          ACTION_COLORS[rec.action] ?? "text-gray-500 bg-gray-100 dark:bg-gray-700"
                        }`}
                      >
                        {rec.action}
                      </span>
                    </td>
                    <td className="py-1.5 px-1 text-right text-gray-500 dark:text-gray-400">
                      {rec.current_weight.toFixed(1)}%
                    </td>
                    <td className="py-1.5 px-1 text-right font-medium text-gray-700 dark:text-gray-300">
                      {rec.target_weight.toFixed(1)}%
                    </td>
                    <td className="py-1.5 pl-2 text-gray-400 dark:text-gray-500 hidden sm:table-cell max-w-[120px] truncate">
                      {rec.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 요약 */}
      <div className="rounded-xl bg-amber-50 dark:bg-amber-900/10 border border-amber-100 dark:border-amber-800/30 p-3">
        <p className="text-xs text-amber-800 dark:text-amber-300 leading-relaxed">{summary}</p>
      </div>
    </div>
  );
}
