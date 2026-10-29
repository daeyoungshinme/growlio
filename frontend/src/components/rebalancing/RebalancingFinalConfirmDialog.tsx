import { createPortal } from "react-dom";
import type { ExecutionOrderItem } from "@/api/rebalancing";
import ConfirmModal from "@/components/common/ConfirmModal";
import { isOverseasMarket } from "@/constants/markets";
import { LIMIT_DEVIATION_WARN_PCT, limitDeviationPct } from "./rebalancingTradeMath";
import { STRATEGY_OPTIONS } from "@/constants/rebalancingConfig";
import type { ExecutionState, OrderType } from "@/hooks/useRebalancingExecution";
import { fmtKrw, fmtKrwPrice } from "@/utils/format";

const MAX_LISTED_ORDERS = 6;

interface Props {
  orders: ExecutionOrderItem[];
  orderType: OrderType;
  strategy: ExecutionState["strategy"];
  hasRealAccount: boolean;
  livePricesKrw: Record<string, number>;
  livePricesUsd: Record<string, number>;
  totalSellProceeds: number | null;
  totalBuyCost: number | null;
  onConfirm: () => void;
  onCancel: () => void;
}

function fmtNativePrice(price: number, market: string): string {
  return isOverseasMarket(market) ? `$${price.toFixed(2)}` : fmtKrwPrice(price);
}

export function RebalancingFinalConfirmDialog({
  orders,
  orderType,
  strategy,
  hasRealAccount,
  livePricesKrw,
  livePricesUsd,
  totalSellProceeds,
  totalBuyCost,
  onConfirm,
  onCancel,
}: Props) {
  const typeLabel = orderType === "LIMIT" ? "지정가" : "시장가";
  const sellCount = orders.filter((o) => o.side === "SELL").length;
  const buyCount = orders.length - sellCount;
  const strategyLabel = STRATEGY_OPTIONS.find((o) => o.value === strategy)?.label ?? strategy;
  const listed = orders.slice(0, MAX_LISTED_ORDERS);
  const hiddenCount = orders.length - listed.length;

  // body로 포털 — avoidBottomNav 실행 모달(모바일 z-40) 안에 두면 z-[70]이어도 하단 네비(z-50) 아래로 깔린다
  return createPortal(
    <ConfirmModal
      message={`${typeLabel}로 ${orders.length}건을 주문합니다. 실행 후에는 이 화면에서 되돌릴 수 없습니다.`}
      confirmLabel={`${typeLabel} 주문 실행`}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <div className="mt-3 space-y-3 text-xs">
        <p
          className={
            hasRealAccount
              ? "font-medium text-red-600 dark:text-red-400"
              : "text-yellow-700 dark:text-yellow-400"
          }
        >
          {hasRealAccount ? "실계좌 주문 — 실제 자금이 사용됩니다." : "모의투자 주문"}
        </p>

        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-gray-600 dark:text-gray-400">
          <dt>주문 방식</dt>
          <dd className="text-right text-gray-900 dark:text-gray-100">{strategyLabel}</dd>
          {sellCount > 0 && (
            <>
              <dt>매도 {sellCount}건</dt>
              <dd className="text-right text-gray-900 dark:text-gray-100">
                {totalSellProceeds != null ? `약 ${fmtKrw(totalSellProceeds)}` : "—"}
              </dd>
            </>
          )}
          {buyCount > 0 && (
            <>
              <dt>매수 {buyCount}건</dt>
              <dd className="text-right text-gray-900 dark:text-gray-100">
                {totalBuyCost != null ? `약 ${fmtKrw(totalBuyCost)}` : "—"}
              </dd>
            </>
          )}
        </dl>

        <ul className="space-y-1 border-t border-gray-200 dark:border-gray-700 pt-2">
          {listed.map((o) => {
            const dev = limitDeviationPct(o, livePricesKrw, livePricesUsd);
            const farOff = dev != null && Math.abs(dev) > LIMIT_DEVIATION_WARN_PCT;
            return (
              <li
                key={`${o.account_id}-${o.side}-${o.ticker}`}
                className="flex justify-between gap-2"
              >
                <span className="min-w-0 truncate text-gray-800 dark:text-gray-200">
                  <span
                    className={
                      o.side === "SELL"
                        ? "text-blue-600 dark:text-blue-400"
                        : "text-red-600 dark:text-red-400"
                    }
                  >
                    {o.side === "SELL" ? "매도" : "매수"}
                  </span>{" "}
                  {o.name}
                </span>
                <span className="shrink-0 text-right text-gray-700 dark:text-gray-300">
                  {o.quantity}주
                  {o.order_type === "LIMIT" && o.limit_price != null && (
                    <>
                      {" · "}
                      <span
                        className={
                          farOff ? "font-semibold text-amber-600 dark:text-amber-400" : undefined
                        }
                      >
                        {fmtNativePrice(o.limit_price, o.market)}
                        {farOff && ` (현재가 ${dev > 0 ? "+" : ""}${dev.toFixed(1)}%)`}
                      </span>
                    </>
                  )}
                </span>
              </li>
            );
          })}
          {hiddenCount > 0 && (
            <li className="text-gray-500 dark:text-gray-400">외 {hiddenCount}건</li>
          )}
        </ul>

        <p className="rounded-lg bg-amber-50 border border-amber-200 dark:bg-amber-900/20 dark:border-amber-700/40 px-3 py-2 text-amber-800 dark:text-amber-300">
          {orderType === "MARKET"
            ? "시장가는 체결 시점 가격으로 즉시 체결됩니다. 호가가 얇거나 장 초반·마감 직전엔 예상가와 크게 다를 수 있어요."
            : "지정한 가격에 도달하지 않으면 체결되지 않고 미체결로 남을 수 있어요."}
        </p>
      </div>
    </ConfirmModal>,
    document.body,
  );
}
