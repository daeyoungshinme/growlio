import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DividendMonthlyBreakdown, TickerDividendItem } from "../../api/dashboard";
import DividendByTickerTable from "./DividendByTickerTable";
import { useThemeStore } from "../../stores/themeStore";
import { fmtKrw } from "../../utils/format";

interface Props {
  annualReceived: number | null;
  estimatedAnnual: number | null;
  monthlyBreakdown: DividendMonthlyBreakdown[];
  tickerItems?: TickerDividendItem[];
  tickerItemsLoading?: boolean;
}

function StatBox({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4 flex-1">
      <p className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide">{label}</p>
      <p className="text-xl font-bold text-gray-900 dark:text-gray-50 mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function DividendSection({ annualReceived, estimatedAnnual, monthlyBreakdown, tickerItems, tickerItemsLoading }: Props) {
  const hasData = monthlyBreakdown.length > 0;
  const [showTicker, setShowTicker] = useState(false);
  const isDark = useThemeStore((s) => s.isDark);
  const filteredTickerItems = (tickerItems ?? [])
    .filter((d) => d.estimated_annual_krw > 0)
    .sort((a, b) => b.estimated_annual_krw - a.estimated_annual_krw);

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <StatBox
          label="올해 수령 배당금"
          value={annualReceived != null && annualReceived > 0 ? fmtKrw(annualReceived) : "—"}
          sub={annualReceived != null && annualReceived > 0 ? "실제 수령 합계" : "배당 내역을 입력해주세요"}
        />
        <StatBox
          label="예상 연간 배당금"
          value={estimatedAnnual != null && estimatedAnnual > 0 ? fmtKrw(estimatedAnnual) : "—"}
          sub="보유 종목 배당수익률 기준 추정"
        />
      </div>

      {hasData && (
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-2 font-medium">월별 배당 수령 현황</p>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={monthlyBreakdown} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
              <XAxis
                dataKey="month"
                tick={{ fontSize: 10, fill: "#9CA3AF" }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => v.slice(5)}
              />
              <YAxis hide />
              <Tooltip
                formatter={(v: number) => [fmtKrw(v), "배당금"]}
                cursor={{ fill: isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.04)" }}
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 8,
                  border: `1px solid ${isDark ? "#374151" : "#E5E7EB"}`,
                  backgroundColor: isDark ? "#1f2937" : "#ffffff",
                  color: isDark ? "#f9fafb" : "#111827",
                }}
                labelStyle={{ color: isDark ? "#f9fafb" : "#111827" }}
                itemStyle={{ color: isDark ? "#f9fafb" : "#111827" }}
              />
              <Bar dataKey="amount" fill="#16A34A" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {!hasData && (
        <p className="text-xs text-gray-300 dark:text-gray-600 text-center py-2">
          포트폴리오 페이지에서 계좌별 배당금 내역을 추가하면 여기에 표시됩니다
        </p>
      )}

      <div>
        <button
          onClick={() => setShowTicker((v) => !v)}
          className="flex items-center justify-between w-full text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 font-medium transition-colors"
        >
          <span>
            종목별 배당 현황
            {!showTicker && filteredTickerItems.length > 0 && (
              <span className="ml-1 text-gray-300 dark:text-gray-600">({filteredTickerItems.length}개 종목)</span>
            )}
          </span>
          <ChevronDown
            size={14}
            className={`transition-transform duration-200 ${showTicker ? "rotate-180" : ""}`}
          />
        </button>
        {showTicker && (
          <div className="mt-2">
            <DividendByTickerTable
              items={filteredTickerItems}
              isLoading={tickerItemsLoading ?? false}
            />
          </div>
        )}
      </div>
    </div>
  );
}
