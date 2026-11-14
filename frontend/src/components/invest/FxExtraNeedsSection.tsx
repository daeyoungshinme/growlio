import { lazy, Suspense, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCheck, Pencil, Plus, Trash2 } from "lucide-react";
import {
  deleteFxExtraNeed,
  fetchFxExtraNeeds,
  syncFxExtraNeedAlerts,
  updateFxExtraNeed,
  type FxExtraNeed,
} from "@/api/invest";
import type { ExchangeRateAlert } from "@/api/alerts";
import { exchangeRateAlertsQuery } from "@/api/queryOptions";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import AccountActionsMenu from "@/components/common/AccountActionsMenu";
import ConfirmModal from "@/components/common/ConfirmModal";
import SkeletonCard from "@/components/common/SkeletonCard";
import FxTrancheList from "@/components/invest/FxTrancheList";
import { clampPct, fmtUsd, pctOf } from "@/utils/format";
import { planAlertState, syncButtonLabel, syncToastMessage } from "@/utils/fxPlanAlerts";
import { invalidateFxExtraNeedData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

const FxExtraNeedModal = lazy(() => import("@/components/invest/FxExtraNeedModal"));

/** 백엔드 `MAX_FX_EXTRA_NEEDS_PER_USER`와 같은 값 */
const MAX_FX_EXTRA_NEEDS = 10;
/** 필요일까지 이 일수 이하면 남은 금액 전액을 "지금"으로 — 백엔드 `FX_EXTRA_URGENT_DAYS`와 같은 값 */
const FX_EXTRA_URGENT_DAYS = 14;

const fmtUsdWhole = (n: number) => fmtUsd(n, 0);

function dueLabel(need: FxExtraNeed) {
  const [, m, d] = need.due_date.split("-").map(Number);
  const date = `${m}월 ${d}일`;
  if (need.days_left < 0) return `${date} · 지남`;
  if (need.days_left === 0) return `${date} · 오늘`;
  return `${date} · D-${need.days_left}`;
}

interface RowProps {
  need: FxExtraNeed;
  alerts: ExchangeRateAlert[] | undefined;
  onEdit: () => void;
  onDelete: () => void;
  onDone: () => void;
}

function NeedRow({ need, alerts, onEdit, onDelete, onDone }: RowProps) {
  const qc = useQueryClient();
  const plan = planAlertState(alerts, need.tranches, { fxNeedId: need.id });
  const syncMutation = useMutation({
    mutationFn: (targets: { target_rate: number; usd: number }[]) =>
      syncFxExtraNeedAlerts(need.id, targets),
    onSuccess: (result, targets) => {
      void invalidateFxExtraNeedData(qc);
      toast(syncToastMessage(result, targets.length), "success");
    },
    onError: (e) => {
      void invalidateFxExtraNeedData(qc);
      toast(extractErrorMessage(e, "알림 등록에 실패했습니다"), "error");
    },
  });

  const progress = clampPct(pctOf(need.exchanged_usd, need.amount_usd));
  const pastDue = need.status === "PAST_DUE";
  // 서버는 OK 상태에만 구간을 준다 — 다 바꿨거나 지난 항목은 목표가 비어 남은 계획 알림 "해제"만 보인다
  const showSync = plan.targets.length > 0 || plan.planAlertCount > 0;

  return (
    <li className={`space-y-3 py-4 first:pt-0 ${pastDue ? "opacity-70" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
            {need.name}
          </p>
          <p
            className={`text-xs tabular-nums ${
              pastDue
                ? "text-gray-400 dark:text-gray-500"
                : need.days_left <= FX_EXTRA_URGENT_DAYS
                  ? "text-amber-600 dark:text-amber-400"
                  : "text-gray-500 dark:text-gray-400"
            }`}
          >
            {dueLabel(need)}
          </p>
          {need.reserved_account_id && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {need.reserved_account_name ?? "증권 계좌"} 달러 예수금 · 적립 환전 계획에서 제외
            </p>
          )}
        </div>
        <AccountActionsMenu
          ariaLabel={`${need.name} 더 보기`}
          items={[
            { icon: <Pencil size={16} />, label: "수정", onClick: onEdit },
            ...(need.status !== "DONE"
              ? [{ icon: <CheckCheck size={16} />, label: "환전 완료로 표시", onClick: onDone }]
              : []),
            {
              icon: <Trash2 size={16} />,
              label: "삭제",
              onClick: onDelete,
              variant: "danger" as const,
            },
          ]}
        />
      </div>

      <div>
        <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 tabular-nums">
          <span>
            환전 {fmtUsdWhole(need.exchanged_usd)} / {fmtUsdWhole(need.amount_usd)}
          </span>
          {need.remaining_usd > 0 && <span>남은 {fmtUsdWhole(need.remaining_usd)}</span>}
        </div>
        <div
          className="mt-1 h-1.5 rounded-full bg-gray-100 dark:bg-gray-800"
          role="img"
          aria-label={`환전 진행 ${progress.toFixed(0)}%`}
        >
          <div className="h-1.5 rounded-full bg-blue-500" style={{ width: `${progress}%` }} />
        </div>
      </div>

      {need.status === "DONE" ? (
        <p className="text-sm text-emerald-700 dark:text-emerald-300">
          필요한 달러를 모두 바꿨습니다.
        </p>
      ) : pastDue ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          필요일이 지났습니다. 다 쓴 항목은 삭제해 주세요.
        </p>
      ) : need.status === "NO_RATE" ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          환율을 불러오지 못해 구간을 계산하지 않았습니다. 잠시 후 다시 시도해 주세요.
        </p>
      ) : (
        <FxTrancheList
          tranches={need.tranches}
          planRates={plan.planRates}
          manualRates={plan.manualRates}
        />
      )}

      {showSync && (
        <button
          onClick={() => syncMutation.mutate(plan.targets)}
          disabled={!alerts || plan.inSync || syncMutation.isPending}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} w-full sm:w-auto px-4 py-2 text-sm font-medium text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-900 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-950/40 disabled:opacity-50 disabled:cursor-not-allowed transition-colors`}
        >
          {syncButtonLabel(plan, !!alerts, syncMutation.isPending)}
        </button>
      )}
    </li>
  );
}

/**
 * 추가 환전 항목(여행 등, plans/123) — 적립 환전 계획과 따로 계산한다.
 * 증권 계좌에 이미 있는 달러로 이 항목을 채우지 않는다(여행 달러는 보통 은행·트래블카드로 따로 바꾼다).
 * 보관 증권 계좌를 지정하면 반대로 그 계좌의 이미 환전한 금액이 적립 계획 보유 달러에서 빠진다.
 */
export default function FxExtraNeedsSection() {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.fxExtraNeeds,
    queryFn: fetchFxExtraNeeds,
    staleTime: STALE_TIME.FIVE_MINUTES,
  });
  const { data: alerts } = useQuery(exchangeRateAlertsQuery);
  const [editing, setEditing] = useState<FxExtraNeed | "new" | null>(null);
  const [pendingDelete, setPendingDelete] = useState<FxExtraNeed | null>(null);

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteFxExtraNeed(id),
    onSuccess: () => {
      void invalidateFxExtraNeedData(qc);
      toast("추가 환전 항목을 삭제했습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "삭제에 실패했습니다"), "error"),
  });
  const doneMutation = useMutation({
    mutationFn: (need: FxExtraNeed) =>
      updateFxExtraNeed(need.id, { exchanged_usd: need.amount_usd }),
    onSuccess: () => {
      void invalidateFxExtraNeedData(qc);
      toast("환전 완료로 표시했습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "저장에 실패했습니다"), "error"),
  });

  const needs = data?.needs ?? [];
  const atLimit = needs.length >= MAX_FX_EXTRA_NEEDS;

  return (
    <section className="space-y-3 border-t border-gray-100 dark:border-gray-800 pt-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          추가 환전 (여행 등)
        </h3>
        {needs.length > 0 && (
          <button
            onClick={() =>
              atLimit
                ? toast(`추가 환전 항목은 ${MAX_FX_EXTRA_NEEDS}개까지 만들 수 있습니다`, "info")
                : setEditing("new")
            }
            aria-label="추가 환전 항목 추가"
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} gap-1 px-2 py-1 text-sm font-medium text-blue-600 dark:text-blue-400`}
          >
            <Plus size={16} aria-hidden />
            추가
          </button>
        )}
      </div>

      {isLoading ? (
        <SkeletonCard rows={2} />
      ) : isError && !data ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          추가 환전 항목을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.
        </p>
      ) : needs.length === 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-gray-500 dark:text-gray-400">
          <span>여행처럼 날짜가 정해진 달러가 필요하면 따로 계획할 수 있습니다.</span>
          <button
            onClick={() => setEditing("new")}
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} gap-1 px-3 py-1.5 text-sm font-medium text-blue-600 dark:text-blue-400`}
          >
            <Plus size={16} aria-hidden />
            추가 환전 등록
          </button>
        </div>
      ) : (
        <>
          <ul className="divide-y divide-gray-100 dark:divide-gray-800">
            {needs.map((need) => (
              <NeedRow
                key={need.id}
                need={need}
                alerts={alerts}
                onEdit={() => setEditing(need)}
                onDelete={() => setPendingDelete(need)}
                onDone={() => doneMutation.mutate(need)}
              />
            ))}
          </ul>
          <p className="text-xs text-gray-400 dark:text-gray-500">
            증권 계좌에 이미 있는 달러로 채우지 않고 따로 계산합니다. 필요일이 2주 안이면 남은
            금액을 지금 바꾸도록 제안합니다. 환전한 뒤 항목의 &lsquo;이미 환전한 금액&rsquo;을 고쳐
            주세요.
          </p>
        </>
      )}

      {editing && (
        <Suspense fallback={null}>
          <FxExtraNeedModal
            need={editing === "new" ? null : editing}
            onClose={() => setEditing(null)}
          />
        </Suspense>
      )}
      {pendingDelete && (
        <ConfirmModal
          message={`'${pendingDelete.name}' 항목을 삭제할까요? 이 항목으로 등록한 목표 환율 알림도 함께 삭제됩니다.`}
          confirmLabel="삭제"
          danger
          onConfirm={() => {
            deleteMutation.mutate(pendingDelete.id);
            setPendingDelete(null);
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </section>
  );
}
