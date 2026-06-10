import { fmtKrw } from "@/utils/format";

interface Props {
  current: number;
  goal: number | null;
  pct: number | null;
}

export default function GoalProgressCard({ current, goal, pct }: Props) {
  if (!goal || pct == null) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-gray-400 dark:text-gray-500 text-sm">
        <p>목표 금액이 설정되지 않았습니다</p>
        <p className="mt-1">설정 페이지에서 목표를 입력해주세요</p>
      </div>
    );
  }

  const clampedPct = Math.min(pct, 100);

  return (
    <div className="flex flex-col items-center gap-4">
      {/* 원형 progress */}
      <div className="relative w-36 h-36">
        <svg viewBox="0 0 36 36" className="w-36 h-36 -rotate-90">
          <circle cx="18" cy="18" r="15.9" fill="none" stroke="#374151" strokeWidth="2.5" className="stroke-gray-200 dark:stroke-gray-700" />
          <circle
            cx="18"
            cy="18"
            r="15.9"
            fill="none"
            stroke="#2563EB"
            strokeWidth="2.5"
            strokeDasharray={`${clampedPct} ${100 - clampedPct}`}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold text-blue-600 dark:text-blue-400">{clampedPct.toFixed(1)}%</span>
          <span className="text-xs text-gray-400 dark:text-gray-500">달성</span>
        </div>
      </div>

      <div className="text-center">
        <p className="text-sm text-gray-500 dark:text-gray-400">현재 자산</p>
        <p className="text-xl font-bold text-gray-900 dark:text-gray-50">{fmtKrw(current)}</p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">목표: {fmtKrw(goal)}</p>
        <p className="text-xs text-gray-400 dark:text-gray-500">남은 금액: {fmtKrw(Math.max(goal - current, 0))}</p>
      </div>
    </div>
  );
}
