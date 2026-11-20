import type { CashAnalysis } from "@/hooks/useRebalancingExecution";
import { fmtKrwPrice, fmtUsd } from "@/utils/format";

export function CashSummaryBar({ analysis }: { analysis: CashAnalysis }) {
  const { deposit, isOrderableKnown, sellProceeds, totalAvailable, buyCost, surplus } = analysis;
  if (deposit === null) return null;
  // null(시세 미확인)은 0과 같이 "표시 안 함"으로 본다
  const sell = sellProceeds ?? 0;
  const buy = buyCost ?? 0;
  const hasSell = sell > 0;
  const hasBuy = buy > 0;
  return (
    <div className="border-b border-gray-200 dark:border-gray-700/30 bg-gray-50 dark:bg-gray-900/20">
      <div className="px-4 py-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs">
        <span className="text-gray-500 dark:text-gray-500">
          {isOrderableKnown ? "주문가능" : "예수금"}{" "}
          <span className="text-gray-700 dark:text-gray-300">{fmtKrwPrice(deposit)}</span>
          {!isOrderableKnown && (
            <span className="text-gray-500 dark:text-gray-600 ml-1">
              (미체결 주문 시 차이 발생)
            </span>
          )}
        </span>
        {hasSell && (
          <span className="text-gray-500 dark:text-gray-500">
            + 매도예상{" "}
            <span className="text-blue-600 dark:text-blue-400">+{fmtKrwPrice(sell)}</span>
          </span>
        )}
        {hasSell && totalAvailable !== null && (
          <span className="text-gray-500 dark:text-gray-500">
            = 사용가능{" "}
            <span className="text-gray-800 dark:text-gray-200">{fmtKrwPrice(totalAvailable)}</span>
          </span>
        )}
        {hasBuy && <span className="text-gray-400 dark:text-gray-600">|</span>}
        {hasBuy && (
          <span className="text-gray-500 dark:text-gray-500">
            매수필요 <span className="text-red-600 dark:text-red-400">{fmtKrwPrice(buy)}</span>
          </span>
        )}
        {surplus !== null && hasBuy && (
          <span
            className={
              surplus >= 0
                ? "text-green-600 dark:text-green-400"
                : "text-amber-600 dark:text-amber-400"
            }
          >
            {surplus >= 0
              ? `여유 +${fmtKrwPrice(surplus)}`
              : `부족 ${fmtKrwPrice(Math.abs(surplus))}`}
          </span>
        )}
      </div>
      <UsdLine analysis={analysis} />
    </div>
  );
}

/** 달러 예수금과 해외 매수 판정(키움 — 달러 우선, 원화주문 계좌만 원화, plans/140) */
function UsdLine({ analysis }: { analysis: CashAnalysis }) {
  const { depositUsd, usd, krwOverseasOrder } = analysis;
  if (depositUsd === null) return null;
  const hasUsdBuy = usd !== null && usd.required > 0;
  return (
    <div className="px-4 pb-1.5 space-y-0.5 text-xs">
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        <span className="text-gray-500 dark:text-gray-500">
          달러 예수금 <span className="text-gray-700 dark:text-gray-300">{fmtUsd(depositUsd)}</span>
        </span>
        {hasUsdBuy && (
          <span className="text-gray-500 dark:text-gray-500">
            해외 매수필요{" "}
            <span className="text-red-600 dark:text-red-400">{fmtUsd(usd.required)}</span>
          </span>
        )}
      </div>
      {hasUsdBuy && usd.shortfall > 0 && (
        <p className="text-amber-600 dark:text-amber-400">
          {krwOverseasOrder
            ? `달러가 ${fmtUsd(usd.shortfall)} 모자라 부족분은 원화(약 ${fmtKrwPrice(usd.krwForUsdShortfall)})로 결제됩니다(원화주문).`
            : `달러가 ${fmtUsd(usd.shortfall)} 모자라 일부 해외 매수는 주문하지 않고 건너뜁니다. 환전하거나, 키움 원화주문을 신청했다면 계좌관리에서 '원화주문'을 켜세요.`}
        </p>
      )}
    </div>
  );
}
