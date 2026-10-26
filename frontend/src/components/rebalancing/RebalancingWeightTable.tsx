import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { RebalancingItem } from "@/api/rebalancing";
import { PROFIT_COLOR, LOSS_COLOR } from "@/utils/colors";
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
  flattenTradeItems,
  isGroupItem,
  isTradableItem,
  TRADING_FEE_RATE,
} from "./rebalancingTradeMath";

function GroupBadge() {
  return (
    <span className="text-[11px] font-medium text-indigo-700 bg-indigo-50 dark:text-indigo-300 dark:bg-indigo-900/40 px-1.5 py-0.5 rounded shrink-0">
      지수
    </span>
  );
}

// 지수 그룹(plans/74) 멤버별 매매 — 그룹 차이를 대표 종목 매수/비대표 멤버 우선 매도로 나눈 결과
function GroupMemberLines({ item }: { item: RebalancingItem }) {
  return (
    <ul className="space-y-0.5">
      {(item.members ?? []).map((m) => {
        const signed = calcSignedTradeKrw(m);
        const shares = m.shares_to_trade;
        const label =
          m.target_value_krw === m.current_value_krw
            ? "유지"
            : `${signed > 0 ? "매수" : "매도"}${shares ? ` ${Math.abs(Math.round(shares))}주` : ""} · ${signed > 0 ? "+" : ""}${fmtKrw(signed)}`;
        return (
          <li
            key={`${m.ticker}-${m.market}`}
            className="flex justify-between gap-2 text-xs text-gray-500 dark:text-gray-400"
          >
            <span className="truncate">
              {m.name} <span className="text-gray-400 dark:text-gray-500">{m.ticker}</span>
              {(m.leverage ?? 1) > 1 && ` · ${m.leverage}배`}
              {m.group_role === "PRIMARY" && " · 대표"}
              {m.group_role === "DOMESTIC_ALT" && " · 국내 대체"}
            </span>
            <span className="shrink-0 tabular-nums">
              {fmtKrw(m.current_value_krw)} · {label}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

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

/** 모바일 항목 카드 — 1줄: 무엇을 할지(매수/매도 N주 · 금액), 2줄: 현재→목표 비중.
 * 가격×수량·수수료·보유 주수는 탭해서 펼친다. 예전엔 약 8개 숫자가 모두 text-xs로 한꺼번에 보였고
 * 비중 막대·차이 배지가 같은 비교를 반복했다 (docs/plans/67 Phase 3). */
function RebalancingItemMobileCard({ item }: { item: RebalancingItem }) {
  const [open, setOpen] = useState(false);
  const isUntracked = item.target_weight_pct === 0 && item.diff_krw < 0;
  const signedKrw = calcSignedTradeKrw(item);
  const shares = item.shares_to_trade;
  const hasTrade = signedKrw !== 0;
  const isBuy = signedKrw > 0;
  const action = !hasTrade
    ? "유지"
    : `${isBuy ? "매수" : "매도"}${shares ? ` ${Math.abs(Math.round(shares))}주` : ""}`;
  const isGroup = isGroupItem(item);
  const hasDetail = isGroup || (isTradableItem(item) && (shares ?? 0) !== 0);

  return (
    <div className="py-2.5 px-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={!hasDetail}
        aria-expanded={hasDetail ? open : undefined}
        className="w-full text-left min-h-[44px] disabled:cursor-default"
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 min-w-0">
            <p className="font-medium text-gray-900 dark:text-gray-100 truncate text-sm">
              {item.name}
            </p>
            {isGroup && <GroupBadge />}
            {isUntracked && (
              <span className="text-xs text-amber-600 dark:text-amber-500 shrink-0">목표 외</span>
            )}
          </div>
          <p
            className={`shrink-0 text-sm font-semibold tabular-nums ${
              !hasTrade ? "text-gray-500 dark:text-gray-400" : isBuy ? PROFIT_COLOR : LOSS_COLOR
            }`}
          >
            {action}
            {hasTrade && (
              <span className="font-normal">
                {" · "}
                {isBuy ? "+" : ""}
                {fmtKrw(signedKrw)}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center justify-between gap-2 mt-0.5">
          <p className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
            {item.current_weight_pct.toFixed(1)}% → 목표 {item.target_weight_pct.toFixed(1)}%
          </p>
          <span className="flex items-center gap-1 shrink-0">
            <WeightDiffBadge diff={item.weight_diff_pct} />
            {hasDetail && (
              <ChevronDown
                size={14}
                className={`text-gray-400 transition-transform ${open ? "rotate-180" : ""}`}
              />
            )}
          </span>
        </div>
      </button>
      {open && isGroup && (
        <div className="mt-1 pl-0.5">
          <GroupMemberLines item={item} />
        </div>
      )}
      {open && hasDetail && !isGroup && (
        <div className="mt-1 pl-0.5 space-y-0.5">
          <p className="text-xs text-gray-500 dark:text-gray-400">{item.ticker}</p>
          {item.current_qty != null && item.target_qty != null && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              보유 {item.current_qty.toFixed(0)}주 → {item.target_qty.toFixed(0)}주
            </p>
          )}
          <TradeExecutionDetail item={item} />
        </div>
      )}
    </div>
  );
}

function RebalancingItemRow({ item, nested = false }: { item: RebalancingItem; nested?: boolean }) {
  const isUntracked = !nested && item.target_weight_pct === 0 && item.diff_krw < 0;
  const isGroup = isGroupItem(item);
  return (
    <tr
      className={`border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 group ${nested ? "text-xs" : ""}`}
    >
      <td
        className={`${nested ? "py-2 pl-7 pr-3" : "py-3.5 px-3"} sticky left-0 bg-white dark:bg-gray-900 group-hover:bg-gray-50 dark:group-hover:bg-gray-700 transition-colors`}
      >
        <div className="flex items-center gap-1.5 font-medium text-gray-900 dark:text-gray-100 max-w-[180px]">
          <span className="truncate">{item.name}</span>
          {isGroup && <GroupBadge />}
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400">
          {isGroup
            ? `${item.members?.length ?? 0}개 종목 합산${item.members?.some((m) => (m.leverage ?? 1) > 1) ? " · 노출 기준" : ""}`
            : `${item.ticker}${(item.leverage ?? 1) > 1 ? ` · ${item.leverage}배` : ""}${item.group_role === "PRIMARY" ? " · 대표" : item.group_role === "DOMESTIC_ALT" ? " · 국내 대체" : ""}`}
        </div>
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
  const unpricedItems = flattenTradeItems(items).filter(
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
            {items.flatMap((item, idx) => [
              <RebalancingItemRow key={idx} item={item} />,
              ...(isGroupItem(item) ? (item.members ?? []) : []).map((m) => (
                <RebalancingItemRow key={`${idx}-${m.ticker}-${m.market}`} item={m} nested />
              )),
            ])}
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
