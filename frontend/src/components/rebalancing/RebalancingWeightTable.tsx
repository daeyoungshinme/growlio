import { RebalancingItem } from "@/api/rebalancing";
import { fmtKrw } from "@/utils/format";
import { CASH_EQUIVALENT_TICKER, CASH_TICKER } from "@/constants/assets";
import {
  DiffCell,
  QuantityCell,
  Return10yCell,
  WeightBar,
  WeightDiffBadge,
} from "./RebalancingCells";
import {
  calcSignedTradeKrw,
  calcTradeKrw,
  isTradableItem,
  TRADING_FEE_RATE,
} from "./rebalancingTradeMath";

// 매매 가능 종목의 실제 거래 내역(가격×수량 + 수수료) — 모바일/데스크탑 공용
function TradeExecutionDetail({ item }: { item: RebalancingItem }) {
  if (!isTradableItem(item) || item.shares_to_trade === 0) return null;
  const tradeKrw = calcTradeKrw(item);
  return (
    <div className="text-xs text-gray-500 dark:text-gray-500 mt-0.5">
      {Math.abs(Math.round(item.shares_to_trade!))}주 × {fmtKrw(item.current_price_krw!)} · 수수료{" "}
      {fmtKrw(tradeKrw * TRADING_FEE_RATE)}
    </div>
  );
}

function RebalancingItemMobileCard({ item }: { item: RebalancingItem }) {
  const isUntracked = item.target_weight_pct === 0 && item.diff_krw < 0;
  const weightDiff = item.weight_diff_pct;
  const directionIcon = weightDiff > 0 ? "↑" : weightDiff < 0 ? "↓" : "";
  return (
    <div className="py-3 px-1">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <p className="font-medium text-gray-900 dark:text-gray-100 truncate text-sm">
              {item.name}
            </p>
            {isUntracked && (
              <span className="text-xs text-amber-600 dark:text-amber-500 shrink-0">목표 외</span>
            )}
            {directionIcon && (
              <span
                className={`text-xs shrink-0 ${weightDiff > 0 ? "text-red-600 dark:text-red-400" : "text-blue-600 dark:text-blue-400"}`}
              >
                {directionIcon}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {item.ticker} · 현재 {item.current_weight_pct.toFixed(1)}%
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="text-xs text-gray-500 dark:text-gray-500">
            목표 {item.target_weight_pct.toFixed(1)}%
          </div>
          <DiffCell diff={calcSignedTradeKrw(item)} />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            <QuantityCell item={item} />
          </p>
          <TradeExecutionDetail item={item} />
        </div>
      </div>
      <div className="mt-2">
        <WeightBar current={item.current_weight_pct} target={item.target_weight_pct} />
      </div>
      <div className="mt-1.5">
        <WeightDiffBadge diff={item.weight_diff_pct} />
      </div>
    </div>
  );
}

function RebalancingItemRow({ item }: { item: RebalancingItem }) {
  const isUntracked = item.target_weight_pct === 0 && item.diff_krw < 0;
  return (
    <tr className="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 group">
      <td className="py-3.5 px-3 sticky left-0 bg-white dark:bg-gray-900 group-hover:bg-gray-50 dark:group-hover:bg-gray-700 transition-colors">
        <div className="font-medium text-gray-900 dark:text-gray-100 truncate max-w-[160px]">
          {item.name}
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400">{item.ticker}</div>
        {isUntracked && (
          <div className="text-xs text-amber-600 dark:text-amber-500 mt-0.5">목표 외</div>
        )}
      </td>
      <td className="py-3.5 px-3 text-right text-gray-700 dark:text-gray-300">
        {item.current_weight_pct.toFixed(1)}%
      </td>
      <td className="py-3.5 px-3">
        <WeightBar current={item.current_weight_pct} target={item.target_weight_pct} />
      </td>
      <td className="py-3.5 px-3 text-right">
        <WeightDiffBadge diff={item.weight_diff_pct} />
      </td>
      <td className="py-3.5 px-3 text-right">
        <div className="text-xs text-gray-700 dark:text-gray-300">
          {fmtKrw(item.current_value_krw)}
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-500">
          → {fmtKrw(item.target_value_krw)}
        </div>
      </td>
      <td className="py-3.5 px-3 text-right">
        <DiffCell diff={calcSignedTradeKrw(item)} />
        <TradeExecutionDetail item={item} />
      </td>
      <td className="py-3.5 px-3 text-right">
        <QuantityCell item={item} />
      </td>
      <td className="py-3.5 px-3">
        <Return10yCell item={item} />
      </td>
    </tr>
  );
}

// 리밸런싱 비중 테이블 — 모바일 카드 뷰 + 데스크탑 테이블 뷰 (종목별 거래 실행 정보 포함)
export default function RebalancingWeightTable({ items }: { items: RebalancingItem[] }) {
  const unpricedItems = items.filter(
    (i) =>
      i.diff_krw !== 0 &&
      (i.shares_to_trade === null || !i.current_price_krw) &&
      i.ticker !== CASH_TICKER &&
      i.ticker !== CASH_EQUIVALENT_TICKER,
  );

  return (
    <>
      <div className="sm:hidden divide-y divide-gray-200 dark:divide-gray-700">
        {items.map((item, idx) => (
          <RebalancingItemMobileCard key={idx} item={item} />
        ))}
      </div>

      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400">
              <th className="text-left py-2 px-3 font-medium sticky left-0 bg-gray-100 dark:bg-gray-800 z-10">
                종목
              </th>
              <th className="text-right py-2 px-3 font-medium">현재 비중</th>
              <th className="text-left py-2 px-3 font-medium">목표 비중</th>
              <th className="text-right py-2 px-3 font-medium">차이</th>
              <th className="text-right py-2 px-3 font-medium">현재/목표</th>
              <th className="text-right py-2 px-3 font-medium">매수/매도</th>
              <th className="text-right py-2 px-3 font-medium">주수</th>
              <th className="text-right py-2 px-3 font-medium">10년 수익률</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => (
              <RebalancingItemRow key={idx} item={item} />
            ))}
          </tbody>
        </table>
      </div>

      {unpricedItems.length > 0 && (
        <div className="text-xs text-amber-600 dark:text-amber-500/80 px-1 pt-2">
          {unpricedItems.map((i) => i.name).join(", ")} 등 {unpricedItems.length}개 종목은 현재가
          미조회로 거래 계획에서 제외됨
        </div>
      )}
    </>
  );
}
