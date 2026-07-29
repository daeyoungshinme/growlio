import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useThemeStore } from "@/stores/themeStore";
import { fmtKrw, fmtKrwPreview, fmtKrwShort } from "@/utils/format";
import { chartTooltipStyle } from "@/utils/chart";
import {
  buildLumpSumProjectionSeries,
  buildSavingsProjectionSeries,
  futureValueOfLumpSum,
  futureValueOfMonthlySavings,
} from "@/utils/savingsProjection";
import {
  DEFAULT_SAVINGS_LUMP_SUM_AMOUNT,
  DEFAULT_SAVINGS_MONTHLY_AMOUNT,
  DEFAULT_SAVINGS_RETURN_PCT,
  SAVINGS_AMOUNT_PRESETS,
  SAVINGS_LUMP_SUM_PRESETS,
  SAVINGS_RETURN_PRESETS,
} from "@/constants/savingsPresets";
import { INPUT_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";
import Tabs from "@/components/common/Tabs";

const CHART_YEARS = Array.from({ length: 31 }, (_, i) => i); // 0~30년
const STAT_YEARS = [10, 20, 30] as const;
const SAVINGS_MODES = ["적립식", "거치식"] as const;
type SavingsMode = (typeof SAVINGS_MODES)[number];

interface Props {
  flat?: boolean;
}

export default function SavingsSimulatorCard({ flat }: Props) {
  const isDark = useThemeStore((s) => s.isDark);
  const [mode, setMode] = useState<SavingsMode>("적립식");
  const [monthlyAmountInput, setMonthlyAmountInput] = useState(
    String(DEFAULT_SAVINGS_MONTHLY_AMOUNT),
  );
  const [lumpAmountInput, setLumpAmountInput] = useState(String(DEFAULT_SAVINGS_LUMP_SUM_AMOUNT));
  const [returnPct, setReturnPct] = useState(DEFAULT_SAVINGS_RETURN_PCT);

  const isLumpSum = mode === "거치식";
  const monthlyAmount = Math.max(0, Number(monthlyAmountInput) || 0);
  const lumpAmount = Math.max(0, Number(lumpAmountInput) || 0);
  const principalAmount = isLumpSum ? lumpAmount : monthlyAmount;

  const chartData = useMemo(
    () =>
      isLumpSum
        ? buildLumpSumProjectionSeries(lumpAmount, returnPct, CHART_YEARS)
        : buildSavingsProjectionSeries(monthlyAmount, returnPct, CHART_YEARS),
    [isLumpSum, monthlyAmount, lumpAmount, returnPct],
  );

  const stats = STAT_YEARS.map((year) => ({
    year,
    value: isLumpSum
      ? futureValueOfLumpSum(lumpAmount, returnPct, year)
      : futureValueOfMonthlySavings(monthlyAmount, returnPct, year),
  }));
  const totalPrincipalAt30 = isLumpSum ? lumpAmount : monthlyAmount * 12 * 30;
  const valueAt30 = stats[2].value;
  const compoundEffect = valueAt30 - totalPrincipalAt30;

  return (
    <div className={flat ? undefined : "card"}>
      <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-1">
        절약 복리 시뮬레이터
      </h3>
      <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">
        {isLumpSum
          ? "받은 보너스나 목돈을 한 번에 투자하면 복리로 얼마나 커지는지 미리 확인해보세요."
          : "매달 아낀 돈을 투자하면 복리로 얼마나 커지는지 미리 확인해보세요."}
      </p>

      <div className="mb-3">
        <Tabs tabs={SAVINGS_MODES} activeTab={mode} onChange={setMode} variant="pill" fullWidth />
      </div>

      {isLumpSum ? (
        <div className="mb-3">
          <label
            htmlFor="savings-lump-amount"
            className="block mb-1 text-xs text-gray-500 dark:text-gray-400 font-medium"
          >
            한 번에 투자할 목돈
          </label>
          <input
            id="savings-lump-amount"
            type="number"
            inputMode="numeric"
            min={0}
            value={lumpAmountInput}
            onChange={(e) => setLumpAmountInput(e.target.value)}
            placeholder="3000000"
            className={`w-full ${INPUT_SM}`}
          />
          <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mt-1">
            {fmtKrwPreview(lumpAmount)}
          </p>
          <div className="flex gap-1.5 mt-2 flex-wrap">
            {SAVINGS_LUMP_SUM_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => setLumpAmountInput(String(preset.amount))}
                className={`text-xs py-1.5 px-2.5 rounded-full transition-colors ${TOUCH_TARGET_COMPACT_MOBILE_ONLY} ${
                  lumpAmount === preset.amount
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-blue-50 dark:hover:bg-blue-950 hover:text-blue-600 dark:hover:text-blue-400"
                }`}
              >
                {preset.label} ({fmtKrwShort(preset.amount)}원)
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="mb-3">
          <label
            htmlFor="savings-monthly-amount"
            className="block mb-1 text-xs text-gray-500 dark:text-gray-400 font-medium"
          >
            매달 절약할 금액
          </label>
          <input
            id="savings-monthly-amount"
            type="number"
            inputMode="numeric"
            min={0}
            value={monthlyAmountInput}
            onChange={(e) => setMonthlyAmountInput(e.target.value)}
            placeholder="100000"
            className={`w-full ${INPUT_SM}`}
          />
          <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mt-1">
            {fmtKrwPreview(monthlyAmount)}
          </p>
          <div className="flex gap-1.5 mt-2 flex-wrap">
            {SAVINGS_AMOUNT_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => setMonthlyAmountInput(String(preset.amount))}
                className={`text-xs py-1.5 px-2.5 rounded-full transition-colors ${TOUCH_TARGET_COMPACT_MOBILE_ONLY} ${
                  monthlyAmount === preset.amount
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-blue-50 dark:hover:bg-blue-950 hover:text-blue-600 dark:hover:text-blue-400"
                }`}
              >
                {preset.label} ({fmtKrwShort(preset.amount)}원)
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mb-4">
        <p className="mb-1 text-xs text-gray-500 dark:text-gray-400 font-medium">가정 수익률</p>
        <div className="flex gap-1.5">
          {SAVINGS_RETURN_PRESETS.map((preset) => (
            <button
              key={preset.pct}
              type="button"
              onClick={() => setReturnPct(preset.pct)}
              className={`flex-1 text-xs py-1.5 px-2 rounded-lg transition-colors ${TOUCH_TARGET_COMPACT_MOBILE_ONLY} ${
                returnPct === preset.pct
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-blue-50 dark:hover:bg-blue-950"
              }`}
            >
              {preset.label} 연{preset.pct}%
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        {stats.map(({ year, value }) => (
          <div key={year} className="p-2.5 rounded-lg bg-indigo-50 dark:bg-indigo-950 text-center">
            <p className="text-xs text-gray-500 dark:text-gray-400">{year}년 후</p>
            <p className="text-sm sm:text-base font-bold text-indigo-600 dark:text-indigo-400 mt-0.5">
              {fmtKrw(value)}
            </p>
          </div>
        ))}
      </div>

      {principalAmount > 0 && (
        <div className="grid grid-cols-3 gap-2 mb-4 p-2.5 rounded-lg bg-gray-50 dark:bg-gray-800">
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              {isLumpSum ? "초기 투자금" : "총 납입액 (30년)"}
            </p>
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">
              {fmtKrw(totalPrincipalAt30)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">투자 후 금액 (30년)</p>
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">
              {fmtKrw(valueAt30)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">복리 효과</p>
            <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
              +{fmtKrw(compoundEffect)}
            </p>
          </div>
        </div>
      )}

      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 4, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#374151" : "#f0f0f0"} />
          <XAxis
            dataKey="year"
            tick={{ fontSize: 11, fill: isDark ? "#9CA3AF" : "#6b7280" }}
            tickFormatter={(v: number) => `${v}년`}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 11, fill: isDark ? "#9CA3AF" : "#6b7280" }}
            tickFormatter={(v: number) => fmtKrwShort(v)}
            width={48}
          />
          <Tooltip
            formatter={(value: number, name: string) => [
              fmtKrw(value),
              name === "value"
                ? "투자 후 금액"
                : isLumpSum
                  ? "원금(추가 납입 없음)"
                  : "단순 납입 누계",
            ]}
            labelFormatter={(label: number) => `${label}년 후`}
            {...chartTooltipStyle(isDark)}
          />
          <Line type="monotone" dataKey="principal" stroke="#9ca3af" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="value" stroke="#4f46e5" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
      <div className="flex items-center gap-4 flex-wrap mt-2 text-xs text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 border-t-2 border-gray-400" />
          {isLumpSum ? "원금(추가 납입 없음)" : "단순 납입 누계"}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 border-t-2 border-indigo-600" />
          투자 후 금액 (복리)
        </span>
      </div>

      <p className="text-xs text-gray-500 dark:text-gray-400 mt-3 pt-3 border-t border-gray-100 dark:border-gray-800">
        {isLumpSum
          ? "묵혀둔 목돈을 그대로 두는 대신 투자하면, 시간이 지날수록 그 차이가 커집니다."
          : "커피 한 잔, 배달비 한 번을 아껴서 꾸준히 투자하면 그 차이는 시간이 지날수록 커집니다. 지출을 조금만 줄여도 목표 달성이 눈에 띄게 빨라져요."}
      </p>
    </div>
  );
}
