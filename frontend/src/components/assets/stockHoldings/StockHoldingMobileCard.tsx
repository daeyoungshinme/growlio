import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { clampPct, fmtKrwShort, fmtPct } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { weightBarColor } from "@/utils/dividendUtils";
import type { DividendYield } from "@/types";
import { marketLabel } from "@/constants/markets";
import DividendMonthsChips from "./DividendMonthsChips";
import { annualDividendLabel, type Agg } from "./holdings";

function DetailItem({
  label,
  children,
  wide,
}: {
  label: string;
  children: ReactNode;
  /** 배당월 칩처럼 반 칸에 들어가지 않는 값은 한 줄 전체를 쓴다 */
  wide?: boolean;
}) {
  return (
    <div className={`flex items-center justify-between gap-2 min-w-0 ${wide ? "col-span-2" : ""}`}>
      <dt className="text-gray-400 dark:text-gray-500 shrink-0">{label}</dt>
      <dd className="text-gray-700 dark:text-gray-300 tabular-nums text-right min-w-0">
        {children}
      </dd>
    </div>
  );
}

interface Props {
  agg: Agg;
  divData: DividendYield | undefined;
  divLoading: boolean;
  divError: boolean;
  expanded: boolean;
  onToggle: () => void;
}

export default function StockHoldingMobileCard({
  agg,
  divData,
  divLoading,
  divError,
  expanded,
  onToggle,
}: Props) {
  const divReady = !divLoading && !divError && divData;
  const annualDiv = divReady ? annualDividendLabel(divData, agg.total_qty) : null;
  return (
    <>
      {/* 접힌 카드는 2줄만 — 비중 막대·배당률은 펼침 영역으로 옮겨 목록 높이를 줄인다 */}
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="w-full text-left"
      >
        <div className="flex items-start justify-between gap-3">
          <p className="min-w-0 font-semibold text-sm text-gray-900 dark:text-gray-50 truncate">
            {agg.name}
          </p>
          <p className="shrink-0 font-semibold text-base text-gray-900 dark:text-gray-50 tabular-nums leading-tight">
            {fmtKrwShort(agg.total_value_krw)}원
          </p>
        </div>
        <div className="mt-0.5 flex items-center justify-between gap-3 text-xs">
          <p className="min-w-0 truncate text-gray-400 dark:text-gray-500">
            {agg.ticker} · {agg.total_qty.toLocaleString()}주 ·{" "}
            <span className="text-gray-500 dark:text-gray-400 tabular-nums">
              비중 {agg.weight_in_stock.toFixed(1)}%
            </span>
          </p>
          <span className="shrink-0 flex items-center gap-1">
            <span className={`font-medium tabular-nums ${pnlColor(agg.total_pnl)}`}>
              {agg.total_pnl >= 0 ? "+" : ""}
              {fmtKrwShort(agg.total_pnl)}원 · {fmtPct(agg.pnl_pct)}
            </span>
            <ChevronDown
              size={14}
              aria-hidden="true"
              className={`text-gray-400 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
            />
          </span>
        </div>
      </button>
      {expanded && (
        <div className="mt-2.5 rounded-lg bg-gray-50 dark:bg-gray-800 px-3 py-2.5 text-xs">
          <div className="mb-2 flex items-center gap-2">
            <div className="flex-1 h-1.5 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
              <div
                className={`h-full rounded-full ${weightBarColor(agg.weight_in_stock)}`}
                style={{ width: `${clampPct(agg.weight_in_stock)}%` }}
              />
            </div>
            <span className="shrink-0 text-gray-500 dark:text-gray-400 tabular-nums">
              {marketLabel(agg.market)}
            </span>
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5">
            <DetailItem label="평단가">
              {Math.round(agg.weighted_avg_price).toLocaleString()}
            </DetailItem>
            <DetailItem label="현재가">{agg.current_price.toLocaleString()}</DetailItem>
            {divReady && divData.investment_yield > 0 && (
              <DetailItem label="투자배당율">
                <span className="text-green-600 dark:text-green-500">
                  {divData.investment_yield.toFixed(2)}%
                </span>
              </DetailItem>
            )}
            {annualDiv && (
              <DetailItem label="예상 연배당" wide>
                {annualDiv}
              </DetailItem>
            )}
            {divReady && divData.dividend_months.length > 0 && (
              <DetailItem label="배당월" wide>
                <DividendMonthsChips divData={divData} />
              </DetailItem>
            )}
          </dl>
          {agg.sub_positions.length > 1 && (
            <ul className="mt-2.5 pt-2.5 border-t border-gray-200 dark:border-gray-700 space-y-1.5">
              {agg.sub_positions.map((sub) => (
                <li
                  key={`${sub.account_id}-${sub.ticker}`}
                  className="flex items-center justify-between gap-2"
                >
                  <span className="min-w-0 flex items-center gap-1">
                    <span className="truncate text-gray-600 dark:text-gray-300">
                      {sub.account_name}
                    </span>
                    <span className="shrink-0 text-gray-400 dark:text-gray-500">
                      {sub.qty.toLocaleString()}주
                    </span>
                  </span>
                  <span className="shrink-0 tabular-nums text-gray-700 dark:text-gray-300">
                    {fmtKrwShort(sub.value_krw)}원
                    <span className={`ml-1.5 ${pnlColor(sub.pnl)}`}>{fmtPct(sub.pnl_pct)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </>
  );
}
