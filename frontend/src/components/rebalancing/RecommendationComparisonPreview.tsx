import { useQuery } from "@tanstack/react-query";
import {
  fetchPortfolioExpectedMetrics,
  type GoalRecommendationItem,
  type PortfolioExpectedMetrics,
} from "@/api/rebalancing";
import type { PortfolioItem } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { buildWeightDiffRows } from "@/utils/recommendationDrift";
import PortfolioWeightChart from "@/components/portfolio-analysis/PortfolioWeightChart";

function MetricCompareCell({
  label,
  current,
  recommended,
  loading,
}: {
  label: string;
  current: number | null | undefined;
  recommended: number | null;
  loading: boolean;
}) {
  return (
    <div>
      <p className="text-gray-400 dark:text-gray-500">{label}</p>
      <p className="text-gray-700 dark:text-gray-300">
        <span>{loading ? "…" : current != null ? `${current.toFixed(1)}%` : "—"}</span>
        {" → "}
        <span className="text-teal-600 dark:text-teal-400 font-medium">
          {recommended != null ? `${recommended.toFixed(1)}%` : "—"}
        </span>
      </p>
    </div>
  );
}

interface Props {
  recommendedItems: GoalRecommendationItem[];
  currentItems: PortfolioItem[];
  recommendedMetrics: PortfolioExpectedMetrics;
  targetPortfolioId: string;
}

/** "적용" 확인창에 표시되는 비교 미리보기 — 종목별 현재 vs 추천 비중 테이블 + 기대수익률/변동성/
 * 배당수익률 요약. 현재 포트폴리오 쪽 지표는 확인창이 열릴 때만 온디맨드로 조회한다(캐싱 없음). */
export default function RecommendationComparisonPreview({
  recommendedItems,
  currentItems,
  recommendedMetrics,
  targetPortfolioId,
}: Props) {
  const { data: currentMetrics, isLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolioExpectedMetrics(targetPortfolioId),
    queryFn: () => fetchPortfolioExpectedMetrics(targetPortfolioId),
  });

  const rows = buildWeightDiffRows(recommendedItems, currentItems);

  return (
    <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <p className="text-center text-xs text-gray-400 dark:text-gray-500">현재</p>
          <PortfolioWeightChart items={currentItems} />
        </div>
        <div>
          <p className="text-center text-xs text-teal-600 dark:text-teal-400 font-medium">추천</p>
          <PortfolioWeightChart items={recommendedItems} />
        </div>
      </div>
      <div className="max-h-40 overflow-y-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-400 dark:text-gray-500">
              <th className="text-left font-normal pb-1">종목</th>
              <th className="text-right font-normal pb-1">현재</th>
              <th className="text-right font-normal pb-1">추천</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="text-gray-700 dark:text-gray-300">
                <td className="py-0.5 pr-2 truncate max-w-[140px]">{row.name}</td>
                <td className="text-right py-0.5 text-gray-400 dark:text-gray-500">
                  {row.currentWeight != null ? `${row.currentWeight.toFixed(1)}%` : "—"}
                </td>
                <td className="text-right py-0.5 font-medium text-teal-600 dark:text-teal-400">
                  {row.recommendedWeight != null ? `${row.recommendedWeight.toFixed(1)}%` : "0%"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pt-2 border-t border-gray-100 dark:border-gray-800 grid grid-cols-3 gap-2 text-xs">
        <MetricCompareCell
          label="기대수익률"
          current={currentMetrics?.expected_return_pct}
          recommended={recommendedMetrics.expected_return_pct}
          loading={isLoading}
        />
        <MetricCompareCell
          label="변동성"
          current={currentMetrics?.expected_volatility_pct}
          recommended={recommendedMetrics.expected_volatility_pct}
          loading={isLoading}
        />
        <MetricCompareCell
          label="배당수익률"
          current={currentMetrics?.expected_dividend_yield_pct}
          recommended={recommendedMetrics.expected_dividend_yield_pct}
          loading={isLoading}
        />
      </div>
    </div>
  );
}
