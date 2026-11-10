import { useEffect, useMemo, useState } from "react";
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
import ConfirmModal from "@/components/common/ConfirmModal";
import SkeletonCard from "@/components/common/SkeletonCard";
import { OrderResultList } from "./OrderResultList";
import { TOUCH_TARGET_MIN_MOBILE_ONLY, TOUCH_TARGET_ROW } from "@/constants/uiSizes";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { PLAN_LEG_STATUS_LABEL } from "@/constants/rebalancingConfig";
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

function useCountdownLabel(deadlineAt: string): string {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  const diffMs = new Date(deadlineAt).getTime() - now;
  if (diffMs <= 0) return "곧 처리됩니다";
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 60) return `${minutes}분 후`;
  const hours = Math.floor(minutes / 60);
  return `${hours}시간 ${minutes % 60}분 후`;
}

function PendingPlanItemsDetail({ items }: { items: RebalancingPlanLegSummary["items"] }) {
  const priceOf = (item: RebalancingPlanLegSummary["items"][number]) =>
    item.order_type === "LIMIT" && item.limit_price != null
      ? item.limit_price.toLocaleString()
      : (item.reference_price?.toLocaleString() ?? "—");

  return (
    <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
      {/* ── 모바일 카드 뷰 (sm 미만) ── */}
      <div className="sm:hidden divide-y divide-gray-200 dark:divide-gray-800">
        {items.map((item, i) => (
          <div key={i} className="py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-gray-800 dark:text-gray-200">
                {item.name ?? item.ticker}{" "}
                <span className="text-gray-500 dark:text-gray-500">({item.ticker})</span>
              </span>
              <span className="text-gray-500 dark:text-gray-400 shrink-0">
                {item.order_type === "LIMIT" ? "지정가" : "시장가"}
              </span>
            </div>
            <div className="flex items-center justify-between gap-2 mt-1 text-gray-500 dark:text-gray-400">
              <span>{item.quantity.toLocaleString()}주</span>
              <span className="font-mono text-gray-500 dark:text-gray-500">{priceOf(item)}</span>
            </div>
          </div>
        ))}
      </div>

      {/* ── 데스크탑 테이블 뷰 (sm 이상) ── */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 dark:text-gray-500">
              <th className="text-left py-1 pr-3">종목</th>
              <th className="text-right py-1 pr-3">수량</th>
              <th className="text-right py-1 pr-3">주문유형</th>
              <th className="text-right py-1">가격</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i} className="border-t border-gray-200 dark:border-gray-800">
                <td className="py-1.5 pr-3 text-gray-800 dark:text-gray-200">
                  {item.name ?? item.ticker}{" "}
                  <span className="text-gray-500 dark:text-gray-500">({item.ticker})</span>
                </td>
                <td className="py-1.5 pr-3 text-right text-gray-700 dark:text-gray-300">
                  {item.quantity.toLocaleString()}
                </td>
                <td className="py-1.5 pr-3 text-right text-gray-500 dark:text-gray-400">
                  {item.order_type === "LIMIT" ? "지정가" : "시장가"}
                </td>
                <td className="py-1.5 text-right text-gray-500 dark:text-gray-500 font-mono">
                  {priceOf(item)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** 백엔드가 코드로 남기는 leg 사유 → 화면 문구 */
const LEG_ERROR_LABEL: Record<string, string> = {
  market_closed_before_execution: "실행 시점에 장이 닫혀 있어 진행되지 않았어요.",
  fx_wait_expired: "환전 대기 기한이 지나 이번 회차 해외 매수는 진행되지 않았어요.",
};

function fmtUsd(v: number | null | undefined): string {
  return `$${(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** 환전 대기 leg 안내 — 필요/보유 달러와 자동 재확인 기한(plans/120) */
function FxWaitNotice({ leg }: { leg: RebalancingPlanLegSummary }) {
  const until = leg.fx_retry_until ? new Date(leg.fx_retry_until) : null;
  return (
    <p className="text-xs text-amber-700 dark:text-amber-300 mt-1 leading-relaxed">
      달러가 부족해 해외 매수를 기다리고 있어요 (필요 {fmtUsd(leg.required_usd)} · 보유{" "}
      {fmtUsd(leg.available_usd)}). 증권사 앱에서 환전한 뒤 다시 매수를 눌러주세요.
      {until &&
        ` ${until.getMonth() + 1}/${until.getDate()}까지는 미국장 중에 자동으로 다시 확인합니다.`}
    </p>
  );
}

function PendingPlanRow({
  leg,
  onCancel,
  onApprove,
  onRetryFx,
  isPending,
}: {
  leg: RebalancingPlanLegSummary;
  onCancel: () => void;
  onApprove: () => void;
  onRetryFx: () => void;
  isPending: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmingCancel, setConfirmingCancel] = useState(false);
  const [confirmingRetry, setConfirmingRetry] = useState(false);
  const countdown = useCountdownLabel(leg.deadline_at);
  const waitingFx = leg.status === "WAITING_FX";
  const sideLabel = waitingFx ? "환전 대기" : leg.side === "BUY" ? "매수 대기" : "매도 승인대기";
  const sideColor =
    leg.side === "BUY" ? "text-red-600 dark:text-red-400" : "text-blue-600 dark:text-blue-400";
  const itemsSummary = leg.items.map((it) => it.name ?? it.ticker).join(", ");
  const sideKrLabel = leg.side === "BUY" ? "매수" : "매도";

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 flex-wrap text-left px-4 py-3"
      >
        <div className="flex items-center gap-2">
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium bg-gray-100 dark:bg-gray-800 ${sideColor}`}
          >
            {sideLabel}
          </span>
          {leg.partially_executed && (
            <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
              일부 실행
            </span>
          )}
          {leg.portfolio_name && (
            <span className="text-sm text-gray-800 dark:text-gray-200">{leg.portfolio_name}</span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {leg.status === "PENDING" && leg.actionable
              ? countdown
              : (PLAN_LEG_STATUS_LABEL[leg.status] ?? leg.status)}
          </span>
          {open ? (
            <ChevronUp size={14} className="text-gray-500 dark:text-gray-400" />
          ) : (
            <ChevronDown size={14} className="text-gray-500 dark:text-gray-400" />
          )}
        </div>
      </button>
      <div className="px-4 pb-3">
        <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
          {itemsSummary} ({leg.items.length}건)
        </p>
        {leg.error_message && (
          <p className="text-xs text-red-600 dark:text-red-400 mt-1">
            {LEG_ERROR_LABEL[leg.error_message] ?? leg.error_message}
          </p>
        )}
        {waitingFx && <FxWaitNotice leg={leg} />}
        {leg.partially_executed && (
          <p className="text-xs text-amber-700 dark:text-amber-300 mt-1">
            같은 계획의 {leg.side === "BUY" ? "매도" : "매수"} 주문은 이미 체결됐어요. 비중이 한쪽만
            조정된 상태일 수 있으니 포트폴리오 탭에서 다시 분석해 보세요.
          </p>
        )}

        {open && <PendingPlanItemsDetail items={leg.items} />}

        {waitingFx && (
          <div className="flex items-center gap-4 mt-2">
            <button
              onClick={() => setConfirmingRetry(true)}
              disabled={isPending}
              className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} px-3 text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300 disabled:opacity-50`}
            >
              환전했어요, 다시 매수
            </button>
            <button
              onClick={() => setConfirmingCancel(true)}
              disabled={isPending}
              className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} px-3 text-sm text-red-600 dark:text-red-400 hover:text-red-500 dark:hover:text-red-300 disabled:opacity-50`}
            >
              이번 회차 건너뛰기
            </button>
          </div>
        )}

        {leg.status === "PENDING" && leg.actionable && (
          <div className="flex items-center gap-4 mt-2">
            <button
              onClick={() => setConfirming(true)}
              disabled={isPending}
              className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} px-3 text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-500 dark:hover:text-blue-300 disabled:opacity-50`}
            >
              {leg.side === "BUY" ? "지금 매수 실행" : "매도 실행"}
            </button>
            <button
              onClick={() => setConfirmingCancel(true)}
              disabled={isPending}
              className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} px-3 text-sm text-red-600 dark:text-red-400 hover:text-red-500 dark:hover:text-red-300 disabled:opacity-50`}
            >
              {leg.side === "BUY" ? "매수 취소" : "매도 거부"}
            </button>
          </div>
        )}
      </div>

      {confirming && (
        <ConfirmModal
          message={`지금 바로 ${sideKrLabel} ${leg.items.length}건을 실행하시겠습니까? 실거래 주문이라 취소할 수 없습니다.`}
          confirmLabel="실행"
          danger={false}
          onConfirm={() => {
            setConfirming(false);
            onApprove();
          }}
          onCancel={() => setConfirming(false)}
        />
      )}
      {confirmingRetry && (
        <ConfirmModal
          message={`달러를 다시 확인하고, 충분하면 매수 ${leg.items.length}건을 실행합니다. 미국장이 열려 있으면 바로 실거래 주문이 나가 취소할 수 없습니다.`}
          confirmLabel="다시 매수"
          danger={false}
          onConfirm={() => {
            setConfirmingRetry(false);
            onRetryFx();
          }}
          onCancel={() => setConfirmingRetry(false)}
        />
      )}
      {confirmingCancel && (
        <ConfirmModal
          message={`이 ${sideKrLabel} 계획 ${leg.items.length}건을 ${leg.side === "BUY" ? "취소" : "거부"}하시겠습니까? 다시 실행하려면 새 계획이 생성될 때까지 기다려야 합니다.`}
          confirmLabel={leg.side === "BUY" ? "매수 취소" : "매도 거부"}
          onConfirm={() => {
            setConfirmingCancel(false);
            onCancel();
          }}
          onCancel={() => setConfirmingCancel(false)}
        />
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
