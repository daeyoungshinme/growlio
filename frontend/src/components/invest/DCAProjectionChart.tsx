import { memo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DCAProjectionPoint } from "@/api/invest";
import { useThemeStore } from "@/stores/themeStore";
import { fmtKrw, fmtKrwShort } from "@/utils/format";
import { chartTooltipStyle } from "@/utils/chart";
import { buildScenarioCurve } from "@/utils/dcaScenarioProjection";
import { SAVINGS_RETURN_PRESETS } from "@/constants/savingsPresets";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";

const CONSERVATIVE_RETURN_PCT = SAVINGS_RETURN_PRESETS[0].pct;
const AGGRESSIVE_RETURN_PCT = SAVINGS_RETURN_PRESETS[SAVINGS_RETURN_PRESETS.length - 1].pct;

interface Props {
  data: DCAProjectionPoint[];
  monthlyDepositAmount?: number | null;
}

function DCAProjectionChart({ data, monthlyDepositAmount }: Props) {
  const isDark = useThemeStore((s) => s.isDark);
  const [showScenarios, setShowScenarios] = useState(false);
  const canShowScenarios = !!monthlyDepositAmount && monthlyDepositAmount > 0;
  const today = new Date().toISOString().slice(0, 7);
  const pastPoints = data.filter((d) => d.month <= today);
  const futurePoints = data.filter((d) => d.month > today);
  const recentPast = pastPoints.slice(-24);
  const VISIBLE_FUTURE_MONTHS = 36;
  const visibleFuture = futurePoints.slice(0, VISIBLE_FUTURE_MONTHS);
  const hasActualData = data.some((d) => d.actual_krw !== null);
  // 경계점: 마지막 과거 달을 미래 시작점으로도 포함해 실선↔점선이 끊기지 않게
  const boundaryPoint = recentPast.length > 0 ? recentPast[recentPast.length - 1] : null;
  const conservativeCurve =
    showScenarios && canShowScenarios
      ? buildScenarioCurve(data, monthlyDepositAmount!, CONSERVATIVE_RETURN_PCT)
      : {};
  const aggressiveCurve =
    showScenarios && canShowScenarios
      ? buildScenarioCurve(data, monthlyDepositAmount!, AGGRESSIVE_RETURN_PCT)
      : {};

  const chartData = [
    ...recentPast.map((d) => ({ ...d, projected_future_krw: undefined })),
    ...(boundaryPoint
      ? [
          {
            ...boundaryPoint,
            actual_krw: null,
            projected_future_krw: boundaryPoint.projected_krw,
            projected_krw: undefined,
          },
        ]
      : []),
    ...(recentPast.length > 0
      ? visibleFuture.map((d) => ({
          ...d,
          actual_krw: null,
          projected_future_krw: d.projected_krw,
          projected_krw: undefined,
        }))
      : visibleFuture.map((d) => ({ ...d, projected_future_krw: d.projected_krw }))),
  ].map((d) => ({
    ...d,
    conservative_krw: conservativeCurve[d.month],
    aggressive_krw: aggressiveCurve[d.month],
  }));

  const allChartNums = chartData
    .flatMap((d) => {
      const row = d as Record<string, unknown>;
      return [
        row.projected_krw,
        row.projected_future_krw,
        row.actual_krw,
        row.conservative_krw,
        row.aggressive_krw,
      ];
    })
    .filter((v): v is number => typeof v === "number" && isFinite(v));
  const actualNums = chartData
    .map((d) => d.actual_krw)
    .filter((v): v is number => typeof v === "number" && isFinite(v));
  const rawMax = allChartNums.length > 0 ? Math.max(...allChartNums) : 0;
  const actualMax = actualNums.length > 0 ? Math.max(...actualNums) : 0;
  const yMax =
    actualMax > 0 && rawMax > actualMax * 4 ? Math.ceil(actualMax * 3) : Math.ceil(rawMax * 1.05);
  const yDomain: [number, number] = [0, yMax];

  return (
    <div className="card pl-2 sm:pl-5">
      <div className="flex items-center justify-between gap-2 mb-2">
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          이론 복리 곡선 vs 실제 자산
        </h3>
        {canShowScenarios && (
          <button
            type="button"
            onClick={() => setShowScenarios((v) => !v)}
            className={`shrink-0 text-xs py-1 px-2.5 rounded-full transition-colors ${TOUCH_TARGET_COMPACT_MOBILE_ONLY} ${
              showScenarios
                ? "bg-blue-600 text-white"
                : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-blue-50 dark:hover:bg-blue-950"
            }`}
          >
            보수·공격 시나리오 비교
          </button>
        )}
      </div>
      <div className="flex items-center gap-4 flex-wrap mb-3 text-xs text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 border-t-2 border-blue-500" />
          이론 복리 곡선 (과거)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 border-t-2 border-blue-500 border-dashed" />
          이론 복리 곡선 (미래)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-flex items-center gap-0.5">
            <span className="inline-block w-2 h-2 rounded-full bg-red-500" />
            <span className="inline-block w-3 border-t-2 border-red-500" />
          </span>
          실제 자산
        </span>
        {showScenarios && canShowScenarios && (
          <>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-5 border-t-2 border-gray-400 border-dashed" />
              보수적 가정 (연 {CONSERVATIVE_RETURN_PCT}%)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-5 border-t-2 border-violet-500 border-dashed" />
              공격적 가정 (연 {AGGRESSIVE_RETURN_PCT}%)
            </span>
          </>
        )}
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData} margin={{ top: 4, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#374151" : "#f0f0f0"} />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 11, fill: isDark ? "#9CA3AF" : "#6b7280" }}
            tickFormatter={(v: string) => v.slice(2)}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 11, fill: isDark ? "#9CA3AF" : "#6b7280" }}
            tickFormatter={(v: number) => fmtKrwShort(v)}
            width={56}
            domain={yDomain}
          />
          <Tooltip
            formatter={(value: number, name: string) => {
              const label =
                name === "conservative_krw"
                  ? `보수적 가정(연 ${CONSERVATIVE_RETURN_PCT}%)`
                  : name === "aggressive_krw"
                    ? `공격적 가정(연 ${AGGRESSIVE_RETURN_PCT}%)`
                    : name === "projected_krw" || name === "projected_future_krw"
                      ? "이론값"
                      : "실제값";
              return [fmtKrw(value), label];
            }}
            labelFormatter={(label: string) => `${label}`}
            {...chartTooltipStyle(isDark)}
          />
          <Line
            type="monotone"
            dataKey="projected_krw"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="projected_future_krw"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
            strokeDasharray="5 3"
          />
          <Line
            type="monotone"
            dataKey="actual_krw"
            stroke="#ef4444"
            strokeWidth={2}
            dot={{ r: 3, fill: "#ef4444", strokeWidth: 0 }}
            connectNulls={true}
          />
          {showScenarios && canShowScenarios && (
            <>
              <Line
                type="monotone"
                dataKey="conservative_krw"
                stroke="#9ca3af"
                strokeWidth={1.5}
                dot={false}
                strokeDasharray="4 3"
              />
              <Line
                type="monotone"
                dataKey="aggressive_krw"
                stroke="#8b5cf6"
                strokeWidth={1.5}
                dot={false}
                strokeDasharray="4 3"
              />
            </>
          )}
        </LineChart>
      </ResponsiveContainer>
      {!hasActualData && (
        <p className="text-xs text-yellow-500 mt-2">
          실제 자산 데이터가 없습니다. 계좌를 동기화하면 표시됩니다.
        </p>
      )}
    </div>
  );
}

export default memo(DCAProjectionChart);
