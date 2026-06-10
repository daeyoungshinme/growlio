import type { RecommendedAction } from "@/api/aiAnalysis";

interface Props {
  recommendations: RecommendedAction[];
}

const ACTION_BADGE: Record<string, string> = {
  매수: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
  매도: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  비중확대: "bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300",
  비중축소: "bg-sky-100 text-sky-700 dark:bg-sky-900 dark:text-sky-300",
  유지: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
};

const PRIORITY_DOT: Record<string, string> = {
  높음: "bg-red-500",
  보통: "bg-yellow-400",
  낮음: "bg-gray-400",
};

export default function RecommendationList({ recommendations }: Props) {
  if (recommendations.length === 0) return null;

  const sorted = [...recommendations].sort((a, b) => {
    const order: Record<string, number> = { 높음: 0, 보통: 1, 낮음: 2 };
    return (order[a.priority] ?? 3) - (order[b.priority] ?? 3);
  });

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-4 space-y-3">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
        추천 액션 ({sorted.length}개)
      </h3>
      <div className="space-y-2">
        {sorted.map((rec, i) => (
          <div
            key={`${rec.ticker}-${i}`}
            className="flex items-start gap-3 p-3 rounded-xl bg-gray-50 dark:bg-gray-800"
          >
            <span
              className={`mt-0.5 w-2 h-2 rounded-full shrink-0 ${PRIORITY_DOT[rec.priority] ?? "bg-gray-400"}`}
            />
            <div className="flex-1 min-w-0 space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                  {rec.name}
                </span>
                <span className="text-xs text-gray-400">{rec.ticker}</span>
                <span
                  className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    ACTION_BADGE[rec.action] ?? "bg-gray-100 text-gray-600"
                  }`}
                >
                  {rec.action}
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{rec.reason}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
