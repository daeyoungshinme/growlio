export const MONTH_LABELS = [
  "1월", "2월", "3월", "4월", "5월", "6월",
  "7월", "8월", "9월", "10월", "11월", "12월",
];

export function yieldBadgeClass(y: number): string {
  if (y >= 7) return "bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 font-bold";
  if (y >= 4) return "bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400";
  if (y >= 2) return "bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400";
  return "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400";
}

export function dividendFreqInfo(months: number[], isManual: boolean): { label: string; cls: string } {
  const n = months.length;
  if (n === 0) return { label: "미설정", cls: "bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500" };
  if (n === 12) return { label: "월배당", cls: "bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400" };
  if (n === 4) return { label: "분기배당", cls: "bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400" };
  if (n === 2) return { label: "반기배당", cls: "bg-orange-50 dark:bg-orange-950 text-orange-600 dark:text-orange-400" };
  if (n === 1) return { label: "연배당", cls: "bg-purple-50 dark:bg-purple-950 text-purple-600 dark:text-purple-400" };
  if (isManual) return { label: `${n}회/년(수동)`, cls: "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400" };
  return { label: `${n}회/년`, cls: "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400" };
}

export function weightBarColor(pct: number): string {
  if (pct >= 25) return "bg-amber-400";
  if (pct >= 15) return "bg-blue-400";
  if (pct >= 5) return "bg-emerald-400";
  return "bg-gray-400";
}
