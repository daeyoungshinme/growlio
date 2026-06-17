import { TrendingUp } from "lucide-react";
import { fmtKrw } from "@/utils/format";
import { useOptimizationSuggestions } from "@/hooks/useOptimizationSuggestions";

const MONTH_KO = [
  "1월",
  "2월",
  "3월",
  "4월",
  "5월",
  "6월",
  "7월",
  "8월",
  "9월",
  "10월",
  "11월",
  "12월",
];

export default function MonthlyOptimizationCard() {
  const { suggestions, isLoading } = useOptimizationSuggestions();

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-16 bg-gray-100 dark:bg-gray-700 rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  if (!suggestions || suggestions.length === 0) {
    return (
      <div className="py-10 text-center text-sm text-gray-400 dark:text-gray-500">
        배당이 균등하게 분배되어 있습니다. 추가 제안이 없습니다.
      </div>
    );
  }

  const byMonth = suggestions.reduce<Record<number, typeof suggestions>>((acc, item) => {
    if (!acc[item.month]) acc[item.month] = [];
    acc[item.month].push(item);
    return acc;
  }, {});

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-400 dark:text-gray-500">
        배당이 상대적으로 약한 달의 강화 매수 종목을 제안합니다.
      </p>
      {Object.entries(byMonth)
        .sort(([a], [b]) => Number(a) - Number(b))
        .map(([monthStr, items]) => {
          const month = Number(monthStr);
          const currentTotal = items[0]?.current_monthly_total_krw ?? 0;
          return (
            <div
              key={month}
              className="rounded-xl border border-amber-100 dark:border-amber-900/30 bg-amber-50 dark:bg-amber-900/10 p-3"
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-semibold text-amber-700 dark:text-amber-400">
                  {MONTH_KO[month - 1]}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500">
                  현재 {fmtKrw(currentTotal)} / 월
                </span>
              </div>
              <div className="space-y-1.5">
                {items.map((item) => (
                  <div
                    key={`${item.ticker}-${item.market}`}
                    className="flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <TrendingUp
                        size={12}
                        className="text-amber-500 dark:text-amber-400 shrink-0"
                      />
                      <span className="font-medium text-gray-700 dark:text-gray-300">
                        {item.ticker}
                      </span>
                      <span className="text-gray-400 dark:text-gray-500 truncate max-w-[120px]">
                        {item.name}
                      </span>
                      <span className="px-1.5 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 text-[10px]">
                        {item.market}
                      </span>
                    </div>
                    <span className="font-semibold text-green-600 dark:text-green-400 shrink-0">
                      +{fmtKrw(item.estimated_monthly_krw)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
    </div>
  );
}
