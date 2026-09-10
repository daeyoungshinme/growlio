import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import type { Challenge, ChallengeCreatePayload } from "@/api/challenges";
import { fetchAccounts } from "@/api/assets";
import type { SettingsData } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { useChallenges } from "@/hooks/useChallenges";
import { useChallengeMutations } from "@/hooks/useChallengeMutations";
import ChallengeCard from "@/components/invest/ChallengeCard";
import ChallengeFormModal from "@/components/invest/ChallengeFormModal";
import EmptyState from "@/components/common/EmptyState";
import SkeletonCard from "@/components/common/SkeletonCard";
import ConfirmModal from "@/components/common/ConfirmModal";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";

interface Props {
  settings?: SettingsData;
}

export default function ChallengeSection({ settings }: Props) {
  const { data: challenges, isLoading, isError } = useChallenges();
  const { data: accounts } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
    staleTime: STALE_TIME.MEDIUM,
  });
  const { create, update, remove } = useChallengeMutations();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Challenge | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Challenge | null>(null);

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };
  const openEdit = (c: Challenge) => {
    setEditing(c);
    setFormOpen(true);
  };
  const closeForm = () => {
    setFormOpen(false);
    setEditing(null);
  };

  const handleSubmit = (payload: ChallengeCreatePayload) => {
    if (editing) {
      update.mutate(
        {
          id: editing.id,
          payload: {
            title: payload.title,
            target_amount: payload.target_amount ?? null,
            target_pct: payload.target_pct ?? null,
            target_months: payload.target_months ?? null,
            deadline_month: payload.deadline_month ?? null,
            reminder_enabled: payload.reminder_enabled,
          },
        },
        { onSuccess: closeForm },
      );
    } else {
      create.mutate(payload, { onSuccess: closeForm });
    }
  };

  if (isLoading) return <SkeletonCard rows={4} height="h-5" />;
  if (isError)
    return (
      <div className="card">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          챌린지를 불러오지 못했어요. 잠시 후 다시 시도해주세요.
        </p>
      </div>
    );

  const list = challenges ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200">적립 챌린지</h2>
        <button
          type="button"
          onClick={openCreate}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors`}
        >
          <Plus size={15} aria-hidden="true" />새 챌린지
        </button>
      </div>

      {list.length === 0 ? (
        <div className="card">
          <EmptyState
            title="아직 만든 챌린지가 없어요"
            description="매달 입금·수익률·평가금액 목표를 챌린지로 만들어 꾸준히 적립하는 습관을 만들어보세요. 진행률은 기록된 입출금 내역을 기준으로 계산돼요."
            action={{ label: "첫 챌린지 만들기", onClick: openCreate }}
          />
        </div>
      ) : (
        <div className="space-y-4">
          {list.map((c) => (
            <ChallengeCard
              key={c.id}
              challenge={c}
              onEdit={() => openEdit(c)}
              onArchive={() => update.mutate({ id: c.id, payload: { status: "ARCHIVED" } })}
              onDelete={() => setDeleteTarget(c)}
            />
          ))}
        </div>
      )}

      {formOpen && (
        <ChallengeFormModal
          challenge={editing ?? undefined}
          accounts={accounts ?? []}
          settings={settings}
          submitting={create.isPending || update.isPending}
          onClose={closeForm}
          onSubmit={handleSubmit}
        />
      )}

      {deleteTarget && (
        <ConfirmModal
          message={`"${deleteTarget.title}" 챌린지를 삭제할까요?`}
          confirmLabel="삭제"
          danger
          onConfirm={() => {
            remove.mutate(deleteTarget.id);
            setDeleteTarget(null);
          }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
