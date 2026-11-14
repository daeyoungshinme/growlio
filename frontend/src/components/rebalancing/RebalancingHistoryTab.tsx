import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import {
  fetchRebalancingExecutionDetail,
  fetchRebalancingHistory,
  RebalancingExecutionSummary,
} from "@/api/rebalancing";
import {
  approvePlanLeg,
  cancelPlanLeg,
  retryFxPlanLeg,
  fetchRecentPlanLegs,
  type RebalancingPlanLegSummary,
} from "@/api/rebalancingPlan";
import SkeletonCard from "@/components/common/SkeletonCard";
import { OrderResultList } from "./OrderResultList";
import PendingPlanRow from "./PendingPlanRow";
import { TOUCH_TARGET_ROW } from "@/constants/uiSizes";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { invalidateRebalancingPlanData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";
import { fmtDateTime } from "@/utils/format";
import { STALE_TIME } from "@/constants/queryConfig";
import { notificationSettingsUrl } from "@/utils/tabUrl";
import EmptyState from "@/components/common/EmptyState";

const TRIGGER_LABEL: Record<string, string> = {
  MANUAL: "수동",
  AUTO: "자동",
};

const TRIGGER_COLOR: Record<string, string> = {
  MANUAL: "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300",
  AUTO: "bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300",
};

const STRATEGY_LABEL: Record<string, string> = {
  FULL: "매도+매수",
  BUY_ONLY: "매수만",
  // 설정 화면의 "2단계 자동실행"은 수동 실행 기록에 붙으면 어긋나 실행 방식만 적는다(plans/90 B4)
  TWO_PHASE: "2단계 매수·매도",
};

function ExecutionRow({ item }: { item: RebalancingExecutionSummary }) {
  const [open, setOpen] = useState(false);

  const { data: detail, isLoading: loadingDetail } = useQuery({
    queryKey: QUERY_KEYS.rebalancingExecutionDetail(item.id),
    queryFn: () => fetchRebalancingExecutionDetail(item.id),
    enabled: open,
    staleTime: Infinity,
  });

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left"
      >
        <div className="flex items-center gap-3 flex-wrap">
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${TRIGGER_COLOR[item.triggered_by] ?? "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300"}`}
          >
            {TRIGGER_LABEL[item.triggered_by] ?? item.triggered_by}
          </span>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {STRATEGY_LABEL[item.strategy] ?? item.strategy}
          </span>
          <span className="text-sm text-gray-800 dark:text-gray-200">
            {fmtDateTime(item.executed_at)}
          </span>
        </div>
        <div className="flex items-center gap-4 shrink-0">
          <div className="flex gap-3 text-xs">
            {item.total_success > 0 && (
              <span className="text-emerald-600 dark:text-emerald-400">
                성공 {item.total_success}
              </span>
            )}
            {item.total_fail > 0 && (
              <span className="text-red-600 dark:text-red-400">실패 {item.total_fail}</span>
            )}
            {item.total_skipped > 0 && (
              <span className="text-gray-500 dark:text-gray-500">건너뜀 {item.total_skipped}</span>
            )}
          </div>
          {open ? (
            <ChevronUp size={14} className="text-gray-500 dark:text-gray-400" />
          ) : (
            <ChevronDown size={14} className="text-gray-500 dark:text-gray-400" />
          )}
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-gray-200 dark:border-gray-700">
          {loadingDetail ? (
            <div className="flex justify-center py-4">
              <Loader2 size={16} className="animate-spin text-gray-500" />
            </div>
          ) : detail?.results ? (
            <div className="mt-3">
              <OrderResultList results={detail.results} />
            </div>
          ) : (
            <p className="text-xs text-gray-500 dark:text-gray-500 mt-3">
              상세 정보를 불러올 수 없습니다.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** 종료된 플랜·실행 이력의 첫 노출 개수 — 최대 30+50개를 한 번에 그려 화면이 끝없이 길었다(docs/plans/67).
 * 대기(PENDING) 플랜은 행동이 필요하므로 개수와 무관하게 항상 전부 보인다. */
const CLOSED_LEGS_VISIBLE = 5;
const HISTORY_PAGE = 10;
const HISTORY_FETCH_SIZE = 50;

export default function RebalancingHistoryTab() {
  const qc = useQueryClient();
  const [showAllLegs, setShowAllLegs] = useState(false);
  const [historyVisible, setHistoryVisible] = useState(HISTORY_PAGE);
  const {
    data: historyPages,
    isLoading,
    isError: historyFailed,
    refetch: refetchHistory,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: QUERY_KEYS.rebalancingHistoryPages,
    queryFn: ({ pageParam }) => fetchRebalancingHistory(HISTORY_FETCH_SIZE, pageParam),
    initialPageParam: 0,
    getNextPageParam: (lastPage, pages) =>
      lastPage.length < HISTORY_FETCH_SIZE ? undefined : pages.length * HISTORY_FETCH_SIZE,
    staleTime: STALE_TIME.SHORT,
  });
  const history = useMemo(() => historyPages?.pages.flat() ?? [], [historyPages]);

  const {
    data: planLegs = [],
    isError: legsFailed,
    refetch: refetchLegs,
  } = useQuery({
    queryKey: QUERY_KEYS.rebalancingPlans,
    queryFn: () => fetchRecentPlanLegs(30),
    staleTime: STALE_TIME.VERY_SHORT,
    // 대기 중(PENDING)인 leg가 있을 때만 30초마다 폴링 — 전부 확정된 상태면 서버 상태가 바뀔 일이
    // 없으므로 탭이 열려 있는 동안 계속 폴링할 필요가 없다. 환전 대기(WAITING_FX)는 30분 자동 재확인이
    // 매수 대기로 되돌리므로 느리게 따라간다(plans/122 C4)
    refetchInterval: (query) => {
      const legs = query.state.data as RebalancingPlanLegSummary[] | undefined;
      if (legs?.some((leg) => leg.status === "PENDING")) return 30_000;
      return legs?.some((leg) => leg.status === "WAITING_FX") ? 120_000 : false;
    },
  });

  // 실패해도 서버 상태는 바뀌었을 수 있다(다시 매수가 기한 경과로 만료 처리 후 409 등) — 목록을 다시 받아
  // 끝난 leg에 버튼이 남지 않게 한다(plans/122 C4)
  const onLegActionError = (e: unknown) => {
    toast(extractErrorMessage(e, "처리 중 오류가 발생했습니다"), "error");
    void invalidateRebalancingPlanData(qc);
  };

  const cancelMut = useMutation({
    mutationFn: (leg: RebalancingPlanLegSummary) => cancelPlanLeg(leg.plan_id, leg.leg_id),
    onSuccess: (res) => {
      toast(res.message, "success");
      void invalidateRebalancingPlanData(qc);
    },
    onError: onLegActionError,
  });

  const approveMut = useMutation({
    mutationFn: (leg: RebalancingPlanLegSummary) => approvePlanLeg(leg.plan_id, leg.leg_id),
    onSuccess: (res) => {
      toast(res.message, res.status === "EXECUTED" ? "success" : "error");
      void invalidateRebalancingPlanData(qc, { executed: res.status === "EXECUTED" });
    },
    onError: onLegActionError,
  });

  const retryFxMut = useMutation({
    mutationFn: (leg: RebalancingPlanLegSummary) => retryFxPlanLeg(leg.plan_id, leg.leg_id),
    onSuccess: (res) => {
      const ok = res.status === "EXECUTED" || res.status === "SCHEDULED";
      toast(res.message, ok ? "success" : "error");
      void invalidateRebalancingPlanData(qc, { executed: res.status === "EXECUTED" });
    },
    onError: onLegActionError,
  });

  const isOpenLeg = (leg: RebalancingPlanLegSummary) =>
    leg.status === "PENDING" || leg.status === "WAITING_FX";
  const pendingLegs = planLegs.filter(isOpenLeg);
  const closedLegs = planLegs.filter((leg) => !isOpenLeg(leg));
  const visibleLegs = showAllLegs
    ? planLegs
    : [...pendingLegs, ...closedLegs.slice(0, CLOSED_LEGS_VISIBLE)];
  const hiddenLegCount = planLegs.length - visibleLegs.length;

  const alertHistoryLink = (
    <Link
      to={notificationSettingsUrl("발송 이력")}
      className="block text-xs text-blue-600 dark:text-blue-400 hover:underline"
    >
      이 화면은 주문 실행 이력이에요 — 알림 발송 이력은 설정에서 확인 →
    </Link>
  );

  if (isLoading) {
    return <SkeletonCard rows={4} />;
  }

  // 실패를 "이력 없음"으로 보이면 대기 매수가 없는 줄 알고 취소 기회를 놓친다
  const loadFailedNotice = (historyFailed || legsFailed) && (
    <EmptyState
      title="실행 이력을 일부 불러오지 못했습니다."
      description="대기 중인 매수가 있어도 여기에 보이지 않을 수 있습니다."
      action={{
        label: "다시 시도",
        onClick: () => {
          void refetchHistory();
          void refetchLegs();
        },
      }}
      compact
    />
  );

  if (history.length === 0 && planLegs.length === 0) {
    if (loadFailedNotice) {
      return (
        <div className="space-y-4">
          {alertHistoryLink}
          {loadFailedNotice}
        </div>
      );
    }
    return (
      <div className="space-y-4">
        {alertHistoryLink}
        <div className="flex flex-col items-center justify-center py-20 text-gray-500 dark:text-gray-500">
          <div className="text-4xl mb-3">📋</div>
          <p className="text-sm">아직 실행 이력이 없습니다.</p>
          <p className="text-xs mt-1">리밸런싱을 실행하면 여기에 기록됩니다.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {alertHistoryLink}
      {loadFailedNotice}
      {planLegs.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
            예약 주문 (대기 · 최근 종료)
          </p>
          {visibleLegs.map((leg) => (
            <PendingPlanRow
              key={leg.leg_id}
              leg={leg}
              onCancel={() => cancelMut.mutate(leg)}
              onApprove={() => approveMut.mutate(leg)}
              onRetryFx={() => retryFxMut.mutate(leg)}
              isPending={cancelMut.isPending || approveMut.isPending || retryFxMut.isPending}
            />
          ))}
          {hiddenLegCount > 0 && (
            <button
              type="button"
              onClick={() => setShowAllLegs(true)}
              className={`${TOUCH_TARGET_ROW} w-full justify-center! text-xs font-medium text-gray-500 dark:text-gray-400`}
            >
              종료된 플랜 {hiddenLegCount}개 더 보기
            </button>
          )}
        </div>
      )}
      {history.length > 0 && (
        <div className="space-y-2">
          {history.slice(0, historyVisible).map((item) => (
            <ExecutionRow key={item.id} item={item} />
          ))}
          {(history.length > historyVisible || hasNextPage) && (
            <button
              type="button"
              disabled={isFetchingNextPage}
              onClick={() => {
                setHistoryVisible((n) => n + HISTORY_PAGE);
                // 받아 둔 만큼 다 보여줬으면 다음 묶음을 받는다
                if (history.length <= historyVisible + HISTORY_PAGE && hasNextPage) {
                  void fetchNextPage();
                }
              }}
              className={`${TOUCH_TARGET_ROW} w-full justify-center! text-xs font-medium text-gray-500 dark:text-gray-400 disabled:opacity-50`}
            >
              {hasNextPage
                ? "실행 이력 더 보기"
                : `실행 이력 더 보기 (${history.length - historyVisible}개 남음)`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
