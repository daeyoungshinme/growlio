import { useQuery } from "@tanstack/react-query";
import {
  Legend,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { fetchFactorAnalysis, fetchPortfolioFactorAnalysis } from "@/api/risk";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { useThemeStore } from "@/stores/themeStore";
import { chartTooltipStyle } from "@/utils/chart";

const FACTOR_LABELS: Record<string, string> = {
  value: "가치",
  growth: "성장",
  size: "소형주",
  momentum: "모멘텀",
};

const FACTOR_KEYS = ["value", "growth", "size", "momentum"] as const;

interface Props {
  selectedPortfolioId?: string;
}

export default function FactorExposureChart({ selectedPortfolioId }: Props) {
  const { isDark } = useThemeStore();

  const { data, isLoading, error } = useQuery({
    queryKey: QUERY_KEYS.factorAnalysis,
    queryFn: fetchFactorAnalysis,
    staleTime: STALE_TIME.LONG,
  });

  const { data: targetData, isLoading: targetLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolioFactorAnalysis(selectedPortfolioId!),
    queryFn: () => fetchPortfolioFactorAnalysis(selectedPortfolioId!),
    staleTime: STALE_TIME.LONG,
    enabled: !!selectedPortfolioId,
  });

  if (isLoading) {
    return (
      <div className="card space-y-3">
        <div className="h-4 w-40 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        <div className="h-52 bg-gray-100 dark:bg-gray-700 rounded-xl animate-pulse" />
        <p className="text-xs text-gray-400 dark:text-gray-500 text-center">
          처음 조회 시 15–30초 소요될 수 있습니다
        </p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="card flex items-center justify-center h-40 text-xs text-gray-400 dark:text-gray-500">
        팩터 데이터를 불러올 수 없습니다
      </div>
    );
  }

  if (data.position_count === 0) {
    return (
      <div className="card flex items-center justify-center h-40 text-xs text-gray-400 dark:text-gray-500">
        포지션 데이터가 없습니다
      </div>
    );
  }

  const radarData = FACTOR_KEYS.map((key) => ({
    factor: FACTOR_LABELS[key],
    current: data.portfolio_factors[key],
    target: targetData?.portfolio_factors[key] ?? null,
    fullMark: 100,
  }));

  const { contentStyle, labelStyle } = chartTooltipStyle(isDark);
  const hasTarget = !!selectedPortfolioId && !!targetData;

  return (
    <div className="card space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">팩터 노출도</h3>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
          Fama-French 기반 · {data.position_count}종목
          {hasTarget && targetLoading && " · 목표 로딩 중..."}
        </p>
      </div>

      <div className="min-h-[200px]">
        <ResponsiveContainer width="100%" height={hasTarget ? 240 : 220}>
          <RadarChart data={radarData} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
            <PolarGrid stroke={isDark ? "#374151" : "#E5E7EB"} />
            <PolarAngleAxis
              dataKey="factor"
              tick={{ fontSize: 11, fill: isDark ? "#9CA3AF" : "#6B7280" }}
            />
            <Radar
              name="현재 포트폴리오"
              dataKey="current"
              stroke="#3B82F6"
              fill="#3B82F6"
              fillOpacity={0.25}
              dot={{ r: 3, fill: "#3B82F6" }}
            />
            {hasTarget && (
              <Radar
                name={targetData?.portfolio_name ?? "목표 포트폴리오"}
                dataKey="target"
                stroke="#F59E0B"
                fill="#F59E0B"
                fillOpacity={0.15}
                dot={{ r: 3, fill: "#F59E0B" }}
              />
            )}
            <Tooltip
              contentStyle={contentStyle}
              labelStyle={labelStyle}
              formatter={(v: number, name: string) => [`${v.toFixed(1)} / 100`, name]}
            />
            {hasTarget && (
              <Legend wrapperStyle={{ fontSize: 11, color: isDark ? "#9CA3AF" : "#6B7280" }} />
            )}
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* 팩터 델타 뱃지 (목표 포트폴리오 선택 시) */}
      {hasTarget && targetData && (
        <div className="grid grid-cols-2 gap-2">
          {FACTOR_KEYS.map((key) => {
            const delta = targetData.portfolio_factors[key] - data.portfolio_factors[key];
            const isUp = delta > 1;
            const isDown = delta < -1;
            return (
              <div
                key={key}
                className="flex items-center justify-between rounded-lg bg-gray-50 dark:bg-gray-700/50 px-2.5 py-1.5 text-xs"
              >
                <span className="font-medium text-gray-700 dark:text-gray-300">
                  {FACTOR_LABELS[key]}
                </span>
                <span
                  className={
                    isUp
                      ? "font-semibold text-amber-600 dark:text-amber-400"
                      : isDown
                        ? "font-semibold text-blue-500"
                        : "text-gray-400 dark:text-gray-500"
                  }
                >
                  {isUp ? "+" : ""}
                  {delta.toFixed(1)}
                  {isUp ? " ↑" : isDown ? " ↓" : " →"}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* 팩터 설명 (목표 비선택 시) */}
      {!hasTarget && (
        <div className="grid grid-cols-2 gap-2 text-xs text-gray-500 dark:text-gray-400">
          <span>
            <span className="font-medium text-gray-700 dark:text-gray-300">가치</span> — 낮은
            P/E·P/B
          </span>
          <span>
            <span className="font-medium text-gray-700 dark:text-gray-300">성장</span> — 높은
            P/E·P/B
          </span>
          <span>
            <span className="font-medium text-gray-700 dark:text-gray-300">소형주</span> — 낮은
            시가총액
          </span>
          <span>
            <span className="font-medium text-gray-700 dark:text-gray-300">모멘텀</span> — 12-1M
            수익률
          </span>
        </div>
      )}

      {/* 상위 종목 팩터 테이블 */}
      {data.holdings.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-700">
                <th className="text-left py-1.5 pr-2 font-medium text-gray-400 dark:text-gray-500">
                  종목
                </th>
                <th className="text-right py-1.5 px-1 font-medium text-gray-400 dark:text-gray-500">
                  P/E
                </th>
                <th className="text-right py-1.5 px-1 font-medium text-gray-400 dark:text-gray-500">
                  P/B
                </th>
                <th className="text-right py-1.5 px-1 font-medium text-gray-400 dark:text-gray-500">
                  모멘텀
                </th>
              </tr>
            </thead>
            <tbody>
              {[...data.holdings]
                .sort((a, b) => b.weight_pct - a.weight_pct)
                .slice(0, 5)
                .map((h) => (
                  <tr
                    key={h.ticker}
                    className="border-b border-gray-50 dark:border-gray-800 last:border-0"
                  >
                    <td className="py-1.5 pr-2 text-gray-700 dark:text-gray-300">
                      <span className="font-medium">{h.ticker}</span>
                      <span className="ml-1 text-gray-400 dark:text-gray-500">
                        {h.weight_pct.toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-1.5 px-1 text-right text-gray-600 dark:text-gray-400">
                      {h.pe_ratio != null ? h.pe_ratio.toFixed(1) : "—"}
                    </td>
                    <td className="py-1.5 px-1 text-right text-gray-600 dark:text-gray-400">
                      {h.pb_ratio != null ? h.pb_ratio.toFixed(2) : "—"}
                    </td>
                    <td
                      className={`py-1.5 px-1 text-right font-medium ${
                        h.momentum_pct == null
                          ? "text-gray-400 dark:text-gray-500"
                          : h.momentum_pct >= 0
                            ? "text-red-500"
                            : "text-blue-500"
                      }`}
                    >
                      {h.momentum_pct != null
                        ? `${h.momentum_pct >= 0 ? "+" : ""}${h.momentum_pct.toFixed(1)}%`
                        : "—"}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-gray-300 dark:text-gray-600">{data.note}</p>
    </div>
  );
}
