import { fmtKrw } from "../../utils/format";

interface Props {
  goal: number | null;
  achievementPct: number | null;
  netDeposits?: number | null;
}

export default function DepositGoalCard({ goal, achievementPct, netDeposits }: Props) {
  if (!goal || achievementPct == null) {
    return (
      <div className="text-center py-4 text-gray-400 dark:text-gray-500 text-sm">
        <p>연간 입금 목표가 설정되지 않았습니다</p>
        <p className="mt-1 text-xs">설정 페이지 &gt; 투자 목표 설정에서 입력해주세요</p>
      </div>
    );
  }

  const clampedPct = Math.min(achievementPct, 100);
  const remaining = Math.max(goal - (netDeposits ?? 0), 0);

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between">
        <div>
          <span className="text-2xl font-bold text-blue-600 dark:text-blue-400">{clampedPct.toFixed(1)}%</span>
          <span className="text-sm text-gray-400 dark:text-gray-500 ml-2">달성</span>
        </div>
        <div className="text-right text-sm text-gray-500 dark:text-gray-400">
          <span className="font-medium text-gray-800 dark:text-gray-200">{netDeposits != null ? fmtKrw(netDeposits) : "—"}</span>
          <span className="text-gray-400 dark:text-gray-500"> / {fmtKrw(goal)}</span>
        </div>
      </div>

      {/* 프로그레스바 */}
      <div className="w-full bg-gray-100 dark:bg-gray-800 rounded-full h-3 overflow-hidden">
        <div
          className="h-full rounded-full bg-blue-500 transition-all duration-500"
          style={{ width: `${clampedPct}%` }}
        />
      </div>

      <div className="flex justify-between text-xs text-gray-400 dark:text-gray-500">
        <span>올해 순입금액</span>
        <span>목표까지 <span className="font-medium text-gray-600 dark:text-gray-300">{fmtKrw(remaining)}</span> 남음</span>
      </div>
    </div>
  );
}
