import { useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { SeriesData } from "@/api/backtest";
import { useThemeStore } from "@/stores/themeStore";
import { chartTooltipStyle } from "@/utils/chart";

const COLORS = [
  "#2563EB",
  "#16A34A",
  "#D97706",
  "#DC2626",
  "#7C3AED",
  "#0891B2",
  "#DB2777",
  "#059669",
];

type ChartView = "cumulative" | "annual" | "drawdown";

interface Props {
  dates: string[];
  series: SeriesData[];
}

function computeDrawdown(values: (number | null)[]): (number | null)[] {
  let peak = -Infinity;
  return values.map((v) => {
    if (v == null) return null;
    if (v > peak) peak = v;
    return peak > 0 ? ((v - peak) / peak) * 100 : null;
  });
}

interface AnnualRow {
  year: string;
  [key: string]: string | number | null;
}

function computeAnnualReturns(dates: string[], series: SeriesData[]): AnnualRow[] {
  // year -> series name -> last non-null value in that year
  const yearLastVal: Map<string, Map<string, number>> = new Map();

  dates.forEach((d, i) => {
    const year = d.slice(0, 4);
    if (!yearLastVal.has(year)) yearLastVal.set(year, new Map());
    const yMap = yearLastVal.get(year)!;
    series.forEach((s) => {
      const v = s.values[i];
      if (v != null) yMap.set(s.name, v);
    });
  });

  const years = Array.from(yearLastVal.keys()).sort();
  const rows: AnnualRow[] = [];

  years.forEach((year, idx) => {
    const row: AnnualRow = { year };
    const curMap = yearLastVal.get(year)!;

    if (idx === 0) {
      // first year: start = first non-null in this year
      const firstIdx = dates.findIndex((d) => d.startsWith(year));
      const firstValMap: Map<string, number> = new Map();
      series.forEach((s) => {
        for (let i = firstIdx; i < dates.length && dates[i].startsWith(year); i++) {
          if (s.values[i] != null) {
            firstValMap.set(s.name, s.values[i]!);
            break;
          }
        }
      });
      series.forEach((s) => {
        const start = firstValMap.get(s.name);
        const end = curMap.get(s.name);
        row[s.name] =
          start != null && end != null && start !== 0
            ? parseFloat(((end / start - 1) * 100).toFixed(2))
            : null;
      });
    } else {
      const prevMap = yearLastVal.get(years[idx - 1])!;
      series.forEach((s) => {
        const start = prevMap.get(s.name);
        const end = curMap.get(s.name);
        row[s.name] =
          start != null && end != null && start !== 0
            ? parseFloat(((end / start - 1) * 100).toFixed(2))
            : null;
      });
    }

    rows.push(row);
  });

  return rows;
}

export default function BacktestResultChart({ dates, series }: Props) {
  const isDark = useThemeStore((s) => s.isDark);
  const [view, setView] = useState<ChartView>("cumulative");

  if (!dates.length || !series.length) return null;

  const tooltipStyle = chartTooltipStyle(isDark);
  const axisProps = {
    tick: { fontSize: 10, fill: "#9CA3AF" },
    axisLine: false as const,
    tickLine: false as const,
  };
  const gridProps = { strokeDasharray: "3 3", stroke: isDark ? "#374151" : "#F3F4F6" };
  const tickInterval = Math.max(1, Math.floor(dates.length / 12));
  const legendStyle = {
    wrapperStyle: { fontSize: 12, paddingTop: 12, color: isDark ? "#d1d5db" : undefined },
  };

  // cumulative line chart data
  const cumulativeData = dates.map((d, i) => {
    const row: Record<string, string | number | undefined> = { date: d.slice(0, 7) };
    series.forEach((s) => {
      const v = s.values[i];
      row[s.name] = v == null ? undefined : v;
    });
    return row;
  });

  // drawdown chart data
  const drawdownData = dates.map((d, i) => {
    const row: Record<string, string | number | undefined> = { date: d.slice(0, 7) };
    series.forEach((s) => {
      const dd = computeDrawdown(s.values);
      const v = dd[i];
      row[s.name] = v == null ? undefined : v;
    });
    return row;
  });

  // annual returns data
  const annualData = computeAnnualReturns(dates, series);

  const btnBase = "px-2.5 py-1 text-xs rounded-lg font-medium transition-colors";
  const btnActive = `${btnBase} bg-blue-600 text-white`;
  const btnInactive = `${btnBase} bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700`;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">
          {view === "cumulative" && "누적 수익률 (기준 = 100)"}
          {view === "annual" && "연도별 수익률"}
          {view === "drawdown" && "드로다운 (최고점 대비 하락률)"}
        </p>
        <div className="flex gap-1">
          <button
            className={view === "cumulative" ? btnActive : btnInactive}
            onClick={() => setView("cumulative")}
          >
            누적
          </button>
          <button
            className={view === "annual" ? btnActive : btnInactive}
            onClick={() => setView("annual")}
          >
            연도별
          </button>
          <button
            className={view === "drawdown" ? btnActive : btnInactive}
            onClick={() => setView("drawdown")}
          >
            드로다운
          </button>
        </div>
      </div>

      {view === "cumulative" && (
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={cumulativeData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="date" {...axisProps} interval={tickInterval} />
            <YAxis {...axisProps} tickFormatter={(v) => `${v.toFixed(0)}`} width={40} />
            <Tooltip
              {...tooltipStyle}
              formatter={(value: unknown, name: string) => {
                if (value == null || typeof value !== "number") return ["-", name];
                return [
                  `${value >= 100 ? "+" : ""}${(value - 100).toFixed(2)}% (${value.toFixed(1)})`,
                  name,
                ];
              }}
            />
            <Legend {...legendStyle} iconType="plainline" />
            {series.map((s, i) => (
              <Line
                key={s.name}
                type="monotone"
                dataKey={s.name}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}

      {view === "annual" && (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={annualData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="year" {...axisProps} />
            <YAxis
              {...axisProps}
              tickFormatter={(v) => `${v > 0 ? "+" : ""}${v.toFixed(0)}%`}
              width={50}
            />
            <ReferenceLine y={0} stroke={isDark ? "#6B7280" : "#D1D5DB"} />
            <Tooltip
              {...tooltipStyle}
              formatter={(value: unknown, name: string) => {
                if (value == null || typeof value !== "number") return ["-", name];
                return [`${value >= 0 ? "+" : ""}${value.toFixed(2)}%`, name];
              }}
            />
            <Legend {...legendStyle} />
            {series.map((s, i) => (
              <Bar
                key={s.name}
                dataKey={s.name}
                fill={COLORS[i % COLORS.length]}
                radius={[2, 2, 0, 0]}
                maxBarSize={28}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}

      {view === "drawdown" && (
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={drawdownData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="date" {...axisProps} interval={tickInterval} />
            <YAxis {...axisProps} tickFormatter={(v) => `${v.toFixed(0)}%`} width={45} />
            <ReferenceLine y={0} stroke={isDark ? "#6B7280" : "#D1D5DB"} />
            <Tooltip
              {...tooltipStyle}
              formatter={(value: unknown, name: string) => {
                if (value == null || typeof value !== "number") return ["-", name];
                return [`${value.toFixed(2)}%`, name];
              }}
            />
            <Legend {...legendStyle} iconType="plainline" />
            {series.map((s, i) => (
              <Area
                key={s.name}
                type="monotone"
                dataKey={s.name}
                stroke={COLORS[i % COLORS.length]}
                fill={`${COLORS[i % COLORS.length]}33`}
                strokeWidth={1.5}
                dot={false}
                connectNulls={false}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
