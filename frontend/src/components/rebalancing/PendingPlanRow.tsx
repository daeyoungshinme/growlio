/** 리밸런싱 이력 탭의 대기 플랜 leg 한 행 — 매수 카운트다운·매도 승인·환전 대기 재매수·취소 확인. */
import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { type RebalancingPlanLegSummary } from "@/api/rebalancingPlan";
import ConfirmModal from "@/components/common/ConfirmModal";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { PLAN_LEG_STATUS_LABEL } from "@/constants/rebalancingConfig";

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

export default function PendingPlanRow({
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
