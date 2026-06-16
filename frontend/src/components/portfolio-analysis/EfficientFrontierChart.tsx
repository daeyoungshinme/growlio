import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Label,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchEfficientFrontier } from "@/api/risk";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { useThemeStore } from "@/stores/themeStore";
import { chartTooltipStyle } from "@/utils/chart";

function CustomTooltip({
  active,
  payload,
  isDark,
}: {
  active?: boolean;
  payload?: { payload: { risk: number; return: number; label?: string } }[];
  isDark: boolean;
}) {
  const { contentStyle } = chartTooltipStyle(isDark);
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={contentStyle} className="rounded-lg px-3 py-2 text-xs space-y-0.5">
      {d.label && <p className="font-medium">{d.label}</p>}
      <p>리스크: <span className="font-medium">{d.risk.toFixed(2)}%</span></p>
      <p>기대수익: <span className="font-medium">{d.return.toFixed(2)}%</span></p>
    </div>
  );
}

interface Props {
  comparePortfolioId?: string;
  comparePortfolioName?: string;
}

export default function EfficientFrontierChart({ comparePortfolioId, comparePortfolioName }: Props) {
  const { isDark } = useThemeStore();
  const { data, isLoading, error } = useQuery({
    queryKey: QUERY_KEYS.efficientFrontier(comparePortfolioId),
    queryFn: () => fetchEfficientFrontier(comparePortfolioId),
    staleTime: STALE_TIME.LONG,
  });

  if (isLoading) {
    return (
      <div className="card space-y-3">
        <div className="h-4 w-48 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        <div className="h-60 bg-gray-100 dark:bg-gray-700 rounded-xl animate-pulse" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="card flex items-center justify-center h-40 text-xs text-gray-400 dark:text-gray-500">
        효율적 프론티어 데이터를 불러올 수 없습니다
      </div>
    );
  }

  if (data.frontier.length === 0) {
    return (
      <div className="card flex flex-col items-center justify-center h-40 gap-1 text-center">
        <p className="text-sm font-medium text-gray-600 dark:text-gray-400">효율적 프론티어</p>
        <p className="text-xs text-gray-400 dark:text-gray-500">{data.note}</p>
      </div>
    );
  }

  const gridColor = isDark ? "#374151" : "#E5E7EB";
  const axisColor = isDark ? "#6B7280" : "#9CA3AF";

  const frontierData = data.frontier.map((p) => ({ ...p, label: undefined as string | undefined }));
  const currentData = data.current ? [{ ...data.current, label: "현재 포트폴리오" }] : [];
  const targetData = data.target
    ? [{ ...data.target, label: comparePortfolioName ?? "목표 포트폴리오" }]
    : [];

  const allRisks = [
    ...data.frontier.map((p) => p.risk),
    ...(data.current ? [data.current.risk] : []),
    ...(data.target ? [data.target.risk] : []),
    ...data.assets.map((a) => a.volatility_pct),
  ];
  const allReturns = [
    ...data.frontier.map((p) => p.return),
    ...(data.current ? [data.current.return] : []),
    ...(data.target ? [data.target.return] : []),
    ...data.assets.map((a) => a.expected_return_pct),
  ];
  const riskMin = Math.max(0, Math.min(...allRisks) - 2);
  const riskMax = Math.max(...allRisks) + 2;
  const retMin = Math.min(...allReturns) - 5;
  const retMax = Math.max(...allReturns) + 5;

  return (
    <div className="card space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">효율적 프론티어</h3>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
          Mean-Variance Optimization · {data.note}
        </p>
      </div>

      <ResponsiveContainer width="100%" height={260}>
        <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
          <CartesianGrid stroke={gridColor} strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="risk"
            name="리스크"
            domain={[riskMin, riskMax]}
            tick={{ fontSize: 10, fill: axisColor }}
            tickFormatter={(v: number) => `${v.toFixed(0)}%`}
          >
            <Label value="연율화 변동성 (%)" offset={-10} position="insideBottom" fontSize={10} fill={axisColor} />
          </XAxis>
          <YAxis
            type="number"
            dataKey="return"
            name="기대수익"
            domain={[retMin, retMax]}
            tick={{ fontSize: 10, fill: axisColor }}
            tickFormatter={(v: number) => `${v.toFixed(0)}%`}
          >
            <Label value="연율화 기대수익률 (%)" angle={-90} position="insideLeft" fontSize={10} fill={axisColor} />
          </YAxis>
          <Tooltip content={<CustomTooltip isDark={isDark} />} />

          {/* 효율적 프론티어 라인 */}
          <Scatter
            name="효율적 프론티어"
            data={frontierData}
            fill="#3B82F6"
            opacity={0.6}
            line={{ stroke: "#3B82F6", strokeWidth: 2 }}
            lineType="joint"
            shape="circle"
          />

          {/* 현재 포트폴리오 */}
          {currentData.length > 0 && (
            <Scatter
              name="현재 포트폴리오"
              data={currentData}
              fill="#EF4444"
              shape="star"
            />
          )}

          {/* 목표 포트폴리오 */}
          {targetData.length > 0 && (
            <Scatter
              name={comparePortfolioName ?? "목표 포트폴리오"}
              data={targetData}
              fill="#F59E0B"
              shape="diamond"
            />
          )}
        </ScatterChart>
      </ResponsiveContainer>

      {/* 범례 */}
      <div className="flex flex-wrap gap-4 text-xs text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-blue-500 inline-block" />
          효율적 프론티어
        </span>
        {data.current && (
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block" />
            현재 포트폴리오
          </span>
        )}
        {data.target && (
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded bg-amber-500 inline-block" />
            {comparePortfolioName ?? "목표 포트폴리오"}
          </span>
        )}
      </div>

      {/* 두 포트폴리오 지표 비교 */}
      {data.current && (
        <div className={`grid gap-3 rounded-xl bg-gray-50 dark:bg-gray-700/50 p-3 text-xs ${data.target ? "grid-cols-2" : "grid-cols-2"}`}>
          <div className="space-y-1.5">
            {data.target && (
              <p className="font-medium text-gray-500 dark:text-gray-400 text-xs">현재 포트폴리오</p>
            )}
            <div>
              <p className="text-gray-400 dark:text-gray-500">변동성</p>
              <p className="font-semibold text-gray-700 dark:text-gray-300">
                {data.current.risk.toFixed(2)}%
              </p>
            </div>
            <div>
              <p className="text-gray-400 dark:text-gray-500">기대수익</p>
              <p className={`font-semibold ${data.current.return >= 0 ? "text-red-500" : "text-blue-500"}`}>
                {data.current.return >= 0 ? "+" : ""}
                {data.current.return.toFixed(2)}%
              </p>
            </div>
          </div>
          {data.target && (
            <div className="space-y-1.5 border-l border-gray-200 dark:border-gray-600 pl-3">
              <p className="font-medium text-amber-600 dark:text-amber-400 text-xs">
                {comparePortfolioName ?? "목표 포트폴리오"}
              </p>
              <div>
                <p className="text-gray-400 dark:text-gray-500">변동성</p>
                <p className="font-semibold text-gray-700 dark:text-gray-300">
                  {data.target.risk.toFixed(2)}%
                  <span className={`ml-1 text-xs ${data.target.risk < data.current.risk ? "text-red-500" : "text-blue-500"}`}>
                    ({data.target.risk < data.current.risk ? "" : "+"}{(data.target.risk - data.current.risk).toFixed(2)}%p)
                  </span>
                </p>
              </div>
              <div>
                <p className="text-gray-400 dark:text-gray-500">기대수익</p>
                <p className={`font-semibold ${data.target.return >= 0 ? "text-red-500" : "text-blue-500"}`}>
                  {data.target.return >= 0 ? "+" : ""}
                  {data.target.return.toFixed(2)}%
                  <span className={`ml-1 text-xs ${data.target.return > data.current.return ? "text-red-500" : "text-blue-500"}`}>
                    ({data.target.return > data.current.return ? "+" : ""}{(data.target.return - data.current.return).toFixed(2)}%p)
                  </span>
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
