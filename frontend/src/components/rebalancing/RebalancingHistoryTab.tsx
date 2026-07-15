import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import {
  fetchRebalancingExecutionDetail,
  fetchRebalancingHistory,
  RebalancingExecutionSummary,
} from "@/api/rebalancing";
import {
  approvePlanLeg,
  cancelPlanLeg,
  fetchRecentPlanLegs,
  type RebalancingPlanLegSummary,
} from "@/api/rebalancingPlan";
import ConfirmModal from "@/components/common/ConfirmModal";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { invalidateRebalancingPlanData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

const TRIGGER_LABEL: Record<string, string> = {
  MANUAL: "수동",
  AUTO: "자동",
};

const TRIGGER_COLOR: Record<string, string> = {
  MANUAL: "bg-gray-700 text-gray-300",
  AUTO: "bg-blue-900 text-blue-300",
};

const STRATEGY_LABEL: Record<string, string> = {
  FULL: "매도+매수",
  BUY_ONLY: "매수만",
};

function ExecutionRow({ item }: { item: RebalancingExecutionSummary }) {
  const [open, setOpen] = useState(false);

  const { data: detail, isLoading: loadingDetail } = useQuery({
    queryKey: [...QUERY_KEYS.rebalancingHistory, item.id],
    queryFn: () => fetchRebalancingExecutionDetail(item.id),
    enabled: open,
    staleTime: Infinity,
  });

  return (
    <div className="border border-gray-700 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-750 transition-colors text-left"
      >
        <div className="flex items-center gap-3 flex-wrap">
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${TRIGGER_COLOR[item.triggered_by] ?? "bg-gray-700 text-gray-300"}`}
          >
            {TRIGGER_LABEL[item.triggered_by] ?? item.triggered_by}
          </span>
          <span className="text-xs text-gray-400">
            {STRATEGY_LABEL[item.strategy] ?? item.strategy}
          </span>
          <span className="text-sm text-gray-200">
            {new Date(item.executed_at).toLocaleString("ko-KR")}
          </span>
        </div>
        <div className="flex items-center gap-4 shrink-0">
          <div className="flex gap-3 text-xs">
            {item.total_success > 0 && (
              <span className="text-emerald-400">성공 {item.total_success}</span>
            )}
            {item.total_fail > 0 && <span className="text-red-400">실패 {item.total_fail}</span>}
            {item.total_skipped > 0 && (
              <span className="text-gray-500">건너뜀 {item.total_skipped}</span>
            )}
          </div>
          {open ? (
            <ChevronUp size={14} className="text-gray-400" />
          ) : (
            <ChevronDown size={14} className="text-gray-400" />
          )}
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-gray-700">
          {loadingDetail ? (
            <div className="flex justify-center py-4">
              <Loader2 size={16} className="animate-spin text-gray-500" />
            </div>
          ) : detail?.results ? (
            detail.results.map((result) => (
              <div key={result.account_id} className="mt-3">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-medium text-gray-300">{result.account_name}</span>
                  {result.is_mock && (
                    <span className="text-xs bg-yellow-900 text-yellow-300 px-1.5 py-0.5 rounded">
                      모의
                    </span>
                  )}
                </div>
                {/* ── 모바일 카드 뷰 (sm 미만) ── */}
                <div className="sm:hidden divide-y divide-gray-800">
                  {result.orders.map((order, i) => (
                    <div key={i} className="py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-gray-200">
                          {order.name} <span className="text-gray-500">({order.ticker})</span>
                        </span>
                        <span
                          className={`font-medium shrink-0 ${order.side === "BUY" ? "text-red-400" : "text-blue-400"}`}
                        >
                          {order.side === "BUY" ? "매수" : "매도"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-2 mt-1 text-gray-400">
                        <span>{order.quantity.toLocaleString()}주</span>
                        <span className="font-mono text-gray-500">{order.order_no ?? "—"}</span>
                        {order.status === "SUCCESS" ? (
                          <span className="text-emerald-400">성공</span>
                        ) : order.status === "FAILED" ? (
                          <span className="text-red-400" title={order.error_msg ?? ""}>
                            실패
                          </span>
                        ) : (
                          <span className="text-gray-500">건너뜀</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {/* ── 데스크탑 테이블 뷰 (sm 이상) ── */}
                <div className="hidden sm:block overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-gray-500">
                        <th className="text-left py-1 pr-3">종목</th>
                        <th className="text-right py-1 pr-3">방향</th>
                        <th className="text-right py-1 pr-3">수량</th>
                        <th className="text-right py-1 pr-3">주문번호</th>
                        <th className="text-right py-1">상태</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.orders.map((order, i) => (
                        <tr key={i} className="border-t border-gray-800">
                          <td className="py-1.5 pr-3 text-gray-200">
                            {order.name} <span className="text-gray-500">({order.ticker})</span>
                          </td>
                          <td
                            className={`py-1.5 pr-3 text-right font-medium ${order.side === "BUY" ? "text-red-400" : "text-blue-400"}`}
                          >
                            {order.side === "BUY" ? "매수" : "매도"}
                          </td>
                          <td className="py-1.5 pr-3 text-right text-gray-300">
                            {order.quantity.toLocaleString()}
                          </td>
                          <td className="py-1.5 pr-3 text-right text-gray-500 font-mono">
                            {order.order_no ?? "—"}
                          </td>
                          <td className="py-1.5 text-right">
                            {order.status === "SUCCESS" ? (
                              <span className="text-emerald-400">성공</span>
                            ) : order.status === "FAILED" ? (
                              <span className="text-red-400" title={order.error_msg ?? ""}>
                                실패
                              </span>
                            ) : (
                              <span className="text-gray-500">건너뜀</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))
          ) : (
            <p className="text-xs text-gray-500 mt-3">상세 정보를 불러올 수 없습니다.</p>
          )}
        </div>
      )}
    </div>
  );
}

const LEG_STATUS_LABEL: Record<string, string> = {
  CANCELED: "취소됨",
  REJECTED: "거부됨",
  EXPIRED: "만료됨",
  FAILED: "실패",
};

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
    <div className="mt-3 pt-3 border-t border-gray-700">
      {/* ── 모바일 카드 뷰 (sm 미만) ── */}
      <div className="sm:hidden divide-y divide-gray-800">
        {items.map((item, i) => (
          <div key={i} className="py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-gray-200">
                {item.name ?? item.ticker} <span className="text-gray-500">({item.ticker})</span>
              </span>
              <span className="text-gray-400 shrink-0">
                {item.order_type === "LIMIT" ? "지정가" : "시장가"}
              </span>
            </div>
            <div className="flex items-center justify-between gap-2 mt-1 text-gray-400">
              <span>{item.quantity.toLocaleString()}주</span>
              <span className="font-mono text-gray-500">{priceOf(item)}</span>
            </div>
          </div>
        ))}
      </div>

      {/* ── 데스크탑 테이블 뷰 (sm 이상) ── */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500">
              <th className="text-left py-1 pr-3">종목</th>
              <th className="text-right py-1 pr-3">수량</th>
              <th className="text-right py-1 pr-3">주문유형</th>
              <th className="text-right py-1">가격</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i} className="border-t border-gray-800">
                <td className="py-1.5 pr-3 text-gray-200">
                  {item.name ?? item.ticker} <span className="text-gray-500">({item.ticker})</span>
                </td>
                <td className="py-1.5 pr-3 text-right text-gray-300">
                  {item.quantity.toLocaleString()}
                </td>
                <td className="py-1.5 pr-3 text-right text-gray-400">
                  {item.order_type === "LIMIT" ? "지정가" : "시장가"}
                </td>
                <td className="py-1.5 text-right text-gray-500 font-mono">{priceOf(item)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PendingPlanRow({
  leg,
  onCancel,
  onApprove,
  isPending,
}: {
  leg: RebalancingPlanLegSummary;
  onCancel: () => void;
  onApprove: () => void;
  isPending: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const countdown = useCountdownLabel(leg.deadline_at);
  const sideLabel = leg.side === "BUY" ? "매수 대기" : "매도 승인대기";
  const sideColor = leg.side === "BUY" ? "text-red-400" : "text-blue-400";
  const itemsSummary = leg.items.map((it) => it.name ?? it.ticker).join(", ");
  const sideKrLabel = leg.side === "BUY" ? "매수" : "매도";

  return (
    <div className="border border-gray-700 rounded-xl px-4 py-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 flex-wrap text-left"
      >
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium bg-gray-800 ${sideColor}`}>
            {sideLabel}
          </span>
          {leg.portfolio_name && (
            <span className="text-sm text-gray-200">{leg.portfolio_name}</span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-gray-400">
            {leg.status === "PENDING" && leg.actionable
              ? countdown
              : (LEG_STATUS_LABEL[leg.status] ?? leg.status)}
          </span>
          {open ? (
            <ChevronUp size={14} className="text-gray-400" />
          ) : (
            <ChevronDown size={14} className="text-gray-400" />
          )}
        </div>
      </button>
      <p className="text-xs text-gray-500 mt-1">
        {itemsSummary} ({leg.items.length}건)
      </p>
      {leg.error_message && <p className="text-xs text-red-400 mt-1">{leg.error_message}</p>}

      {open && <PendingPlanItemsDetail items={leg.items} />}

      {leg.status === "PENDING" && leg.actionable && (
        <div className="flex items-center gap-4 mt-2">
          <button
            onClick={() => setConfirming(true)}
            disabled={isPending}
            className="text-xs font-medium text-blue-400 hover:text-blue-300 disabled:opacity-50"
          >
            {leg.side === "BUY" ? "지금 매수 실행" : "매도 실행"}
          </button>
          <button
            onClick={onCancel}
            disabled={isPending}
            className="text-xs text-red-400 hover:text-red-300 disabled:opacity-50"
          >
            {leg.side === "BUY" ? "매수 취소" : "매도 거부"}
          </button>
        </div>
      )}

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
    </div>
  );
}

export default function RebalancingHistoryTab() {
  const qc = useQueryClient();
  const { data: history = [], isLoading } = useQuery({
    queryKey: QUERY_KEYS.rebalancingHistory,
    queryFn: () => fetchRebalancingHistory(50),
    staleTime: 30_000,
  });

  const { data: planLegs = [] } = useQuery({
    queryKey: QUERY_KEYS.rebalancingPlans,
    queryFn: () => fetchRecentPlanLegs(30),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const cancelMut = useMutation({
    mutationFn: (leg: RebalancingPlanLegSummary) => cancelPlanLeg(leg.plan_id, leg.leg_id),
    onSuccess: (res) => {
      toast(res.message, "success");
      void invalidateRebalancingPlanData(qc);
    },
    onError: (e) => toast(extractErrorMessage(e, "처리 중 오류가 발생했습니다"), "error"),
  });

  const approveMut = useMutation({
    mutationFn: (leg: RebalancingPlanLegSummary) => approvePlanLeg(leg.plan_id, leg.leg_id),
    onSuccess: (res) => {
      toast(res.message, res.status === "EXECUTED" ? "success" : "error");
      void invalidateRebalancingPlanData(qc);
    },
    onError: (e) => toast(extractErrorMessage(e, "처리 중 오류가 발생했습니다"), "error"),
  });

  const alertHistoryLink = (
    <Link
      to="/settings?atab=발송 이력"
      className="block text-xs text-blue-600 dark:text-blue-400 hover:underline"
    >
      이 화면은 주문 실행 이력이에요 — 알림 발송 이력은 설정에서 확인 →
    </Link>
  );

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 size={20} className="animate-spin text-gray-500" />
      </div>
    );
  }

  if (history.length === 0 && planLegs.length === 0) {
    return (
      <div className="space-y-4">
        {alertHistoryLink}
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
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
      {planLegs.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-gray-500">대기중 / 최근 종료된 플랜</p>
          {planLegs.map((leg) => (
            <PendingPlanRow
              key={leg.leg_id}
              leg={leg}
              onCancel={() => cancelMut.mutate(leg)}
              onApprove={() => approveMut.mutate(leg)}
              isPending={cancelMut.isPending || approveMut.isPending}
            />
          ))}
        </div>
      )}
      {history.length > 0 && (
        <div className="space-y-2">
          {history.map((item) => (
            <ExecutionRow key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
