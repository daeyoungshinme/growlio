import type { DividendYield } from "@/types";

/** 배당월 칩 — 12개월이면 "월배당" 하나로 묶는다. */
export default function DividendMonthsChips({ divData }: { divData: DividendYield }) {
  const chipTone = "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400";
  if (divData.dividend_months.length === 12) {
    return <span className={`text-xs px-2 py-0.5 rounded-full ${chipTone}`}>월배당</span>;
  }
  if (divData.dividend_months.length === 0) {
    return <span className="text-gray-300 dark:text-gray-600">—</span>;
  }
  return (
    <div className="flex flex-wrap gap-0.5 justify-end">
      {divData.dividend_months.map((m) => (
        <span key={m} className={`text-xs px-1.5 py-0.5 rounded-full ${chipTone}`}>
          {m}
        </span>
      ))}
    </div>
  );
}
