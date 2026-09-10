import { Flame, Pencil, Archive, Trash2 } from "lucide-react";
import type { Challenge } from "@/api/challenges";
import AccountActionsMenu from "@/components/common/AccountActionsMenu";
import ChallengeMonthGrid from "@/components/invest/ChallengeMonthGrid";
import { fmtKrw, fmtMonth, fmtPct } from "@/utils/format";

const TYPE_LABEL: Record<Challenge["challenge_type"], string> = {
  DEPOSIT: "매달 적립",
  RETURN_PCT: "수익률 목표",
  TARGET_VALUE: "평가금액 목표",
};

const STATUS_LABEL: Record<Challenge["status"], string> = {
  ACTIVE: "진행 중",
  COMPLETED: "달성",
  ARCHIVED: "보관됨",
};

interface Props {
  challenge: Challenge;
  onEdit: () => void;
  onArchive: () => void;
  onDelete: () => void;
}

export default function ChallengeCard({ challenge, onEdit, onArchive, onDelete }: Props) {
  const { progress } = challenge;
  const pct = progress.progress_pct;
  const isDeposit = challenge.challenge_type === "DEPOSIT";
  const hasTarget = isDeposit && challenge.target_amount != null;

  const targetText =
    challenge.challenge_type === "RETURN_PCT"
      ? `목표 수익률 ${fmtPct(challenge.target_pct, 1)}`
      : challenge.challenge_type === "TARGET_VALUE"
        ? `목표 ${fmtKrw(challenge.target_amount ?? 0)}`
        : challenge.target_amount
          ? `매달 ${fmtKrw(challenge.target_amount)}`
          : "매달 입금하기";

  const currentText =
    challenge.challenge_type === "RETURN_PCT"
      ? `현재 ${fmtPct(progress.current_return_pct, 1)}`
      : challenge.challenge_type === "TARGET_VALUE"
        ? `현재 ${fmtKrw(progress.current_value_krw ?? 0)}`
        : null;

  return (
    <div className="card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 truncate">
              {challenge.title}
            </h3>
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
              {TYPE_LABEL[challenge.challenge_type]}
            </span>
            {challenge.status !== "ACTIVE" && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                {STATUS_LABEL[challenge.status]}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {targetText}
            {currentText && ` · ${currentText}`}
            {challenge.deadline_month && ` · ${fmtMonth(challenge.deadline_month)}까지`}
          </p>
        </div>
        <AccountActionsMenu
          ariaLabel="챌린지 메뉴"
          items={[
            { icon: <Pencil size={15} />, label: "편집", onClick: onEdit },
            { icon: <Archive size={15} />, label: "보관", onClick: onArchive },
            { icon: <Trash2 size={15} />, label: "삭제", onClick: onDelete, variant: "danger" },
          ]}
        />
      </div>

      {isDeposit && (
        <div className="mt-3 flex items-center gap-4 text-sm">
          <span className="inline-flex items-center gap-1 font-semibold text-orange-600 dark:text-orange-400">
            <Flame size={16} aria-hidden="true" />
            {progress.current_streak}개월 연속
          </span>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            최장 {progress.longest_streak}개월
          </span>
          <span
            className={`text-xs px-2 py-0.5 rounded-full ${
              progress.this_month_satisfied
                ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
            }`}
          >
            이번 달 {progress.this_month_satisfied ? "완료" : "미완료"}
          </span>
        </div>
      )}

      {pct != null && (
        <div className="mt-3">
          <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
            <span>진행률</span>
            <span className="font-medium text-gray-700 dark:text-gray-200">{pct.toFixed(0)}%</span>
          </div>
          <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
            <div
              className="h-full rounded-full bg-blue-500 transition-all"
              style={{ width: `${Math.min(Math.max(pct, 0), 100)}%` }}
            />
          </div>
        </div>
      )}

      {isDeposit && progress.months.length > 0 && (
        <div className="mt-3">
          <ChallengeMonthGrid months={progress.months} hasTarget={hasTarget} />
        </div>
      )}
    </div>
  );
}
