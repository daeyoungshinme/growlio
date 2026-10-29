import { Fragment } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { clampPct, fmtKrwShort, fmtPct } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import type { DividendYield } from "@/types";
import { marketLabel } from "@/constants/markets";
import DividendMonthsChips from "./DividendMonthsChips";
import {
  annualDividendLabel,
  holdingKey,
  type Agg,
  type AggSortKey,
  type SortState,
} from "./holdings";

function SortTh({
  k,
  label,
  className,
  sort,
  onSort,
}: {
  k: AggSortKey;
  label: string;
  className?: string;
  sort: SortState;
  onSort: (k: AggSortKey) => void;
}) {
  const isActive = sort.key === k;
  return (
    <th
      scope="col"
      role="columnheader"
      tabIndex={0}
      onClick={() => onSort(k)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSort(k)}
      aria-sort={isActive ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
      className={`py-2.5 px-4 text-right text-xs font-medium cursor-pointer select-none uppercase focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
        isActive
          ? "text-blue-600 dark:text-blue-400"
          : "text-gray-400 dark:text-gray-500 hover:text-blue-500 dark:hover:text-blue-400"
      } ${className ?? ""}`}
    >
      {label}
      {isActive ? (sort.dir === "asc" ? " ↑" : " ↓") : ""}
    </th>
  );
}

const PLAIN_TH =
  "py-2.5 px-4 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase";

interface Props {
  rows: Agg[];
  sort: SortState;
  onSort: (k: AggSortKey) => void;
  expanded: Set<string>;
  onToggle: (key: string) => void;
  dividendMap: Record<string, DividendYield>;
  divLoading: boolean;
  divError: boolean;
}

/** 배당 두 칸(투자배당율·배당월) — 로딩·오류·데이터 없음 상태를 한곳에서 그린다 */
function DividendCells({
  divData,
  qty,
  divLoading,
  divError,
}: {
  divData: DividendYield | undefined;
  qty: number;
  divLoading: boolean;
  divError: boolean;
}) {
  if (divLoading) {
    return (
      <>
        <td className="py-3 px-4 text-right text-gray-300 text-xs">...</td>
        <td className="py-3 px-4 text-right text-gray-300 text-xs">...</td>
      </>
    );
  }
  if (divError) {
    return (
      <>
        <td className="py-3 px-4 text-right text-xs text-red-400">오류</td>
        <td className="py-3 px-4 text-right text-gray-300">—</td>
      </>
    );
  }
  if (!divData) {
    return (
      <>
        <td className="py-3 px-4 text-right text-gray-300 dark:text-gray-600">—</td>
        <td className="py-3 px-4 text-right text-gray-300 dark:text-gray-600">—</td>
      </>
    );
  }
  const annualDiv = annualDividendLabel(divData, qty);
  return (
    <>
      <td className="py-3 px-4 text-right">
        {divData.investment_yield > 0 ? (
          <>
            <span className="text-xs text-green-600 dark:text-green-400 font-medium">
              {divData.investment_yield.toFixed(2)}%
            </span>
            {annualDiv && <p className="text-xs text-gray-400 mt-0.5">{annualDiv}</p>}
          </>
        ) : (
          <span className="text-gray-300">—</span>
        )}
      </td>
      <td className="py-3 px-3 text-right">
        <DividendMonthsChips divData={divData} />
      </td>
    </>
  );
}

export default function StockHoldingsDesktopTable({
  rows,
  sort,
  onSort,
  expanded,
  onToggle,
  dividendMap,
  divLoading,
  divError,
}: Props) {
  return (
    <div className="hidden sm:block overflow-x-auto max-h-[800px] overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-10">
          <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
            <th
              scope="col"
              className="py-2.5 px-5 text-left text-xs font-medium text-gray-400 dark:text-gray-500 uppercase sticky left-0 z-20 bg-gray-50 dark:bg-gray-800"
            >
              종목
            </th>
            <th scope="col" className={PLAIN_TH}>
              수량
            </th>
            <th scope="col" className={PLAIN_TH}>
              평단가
            </th>
            <th scope="col" className={PLAIN_TH}>
              현재가
            </th>
            <SortTh
              k="total_value_krw"
              label="평가금액"
              className="min-w-[120px]"
              sort={sort}
              onSort={onSort}
            />
            <SortTh k="pnl_pct" label="수익" sort={sort} onSort={onSort} />
            <SortTh k="weight_in_stock" label="비중" sort={sort} onSort={onSort} />
            <th scope="col" className={`${PLAIN_TH} min-w-[130px]`}>
              투자배당율
            </th>
            <th
              scope="col"
              className="py-2.5 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase w-20"
            >
              배당월
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((agg) => {
            const key = holdingKey(agg);
            const isExpanded = expanded.has(key);
            const hasMultiple = agg.sub_positions.length > 1;
            return (
              <Fragment key={key}>
                <tr
                  className={`border-t border-gray-100 dark:border-gray-700 cursor-pointer ${
                    isExpanded
                      ? "bg-blue-50/30 dark:bg-blue-950/20"
                      : "hover:bg-blue-50/20 dark:hover:bg-blue-950/10"
                  }`}
                  onClick={() => onToggle(key)}
                >
                  <td className="py-3 px-5 sticky left-0 z-10 bg-white dark:bg-gray-900 border-r border-gray-100 dark:border-gray-700">
                    <div className="flex items-center gap-2">
                      <span
                        className={`text-gray-400 dark:text-gray-500 ${hasMultiple ? "visible" : "invisible"}`}
                      >
                        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </span>
                      <div>
                        <p className="font-semibold text-sm text-gray-900 dark:text-gray-50">
                          {agg.name}
                        </p>
                        <p className="text-xs text-gray-400 dark:text-gray-500">
                          {agg.ticker} · {marketLabel(agg.market)}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="py-3 px-4 text-right text-xs font-medium">
                    {agg.total_qty.toLocaleString()}
                  </td>
                  <td className="py-3 px-4 text-right text-xs text-gray-500 dark:text-gray-400">
                    {Math.round(agg.weighted_avg_price).toLocaleString()}
                  </td>
                  <td className="py-3 px-4 text-right text-xs font-medium">
                    {agg.current_price.toLocaleString()}
                  </td>
                  <td className="py-3 px-4 text-right text-xs font-semibold">
                    {fmtKrwShort(agg.total_value_krw)}원
                  </td>
                  <td
                    className={`py-3 px-4 text-right text-xs font-medium ${pnlColor(agg.total_pnl)}`}
                  >
                    {agg.total_pnl >= 0 ? "+" : ""}
                    {fmtKrwShort(agg.total_pnl)}원
                    <span className="font-bold">({fmtPct(agg.pnl_pct)})</span>
                  </td>
                  <td className="py-3 px-4 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <div className="w-16 bg-gray-100 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-blue-500 h-full rounded-full"
                          style={{ width: `${clampPct(agg.weight_in_stock)}%` }}
                        />
                      </div>
                      <span className="text-xs text-indigo-500 dark:text-indigo-400 w-10 text-right">
                        {agg.weight_in_stock.toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <DividendCells
                    divData={dividendMap[key]}
                    qty={agg.total_qty}
                    divLoading={divLoading}
                    divError={divError}
                  />
                </tr>

                {isExpanded &&
                  hasMultiple &&
                  agg.sub_positions.map((sub) => (
                    <tr
                      key={`${sub.account_id}-${sub.ticker}`}
                      className="bg-gray-50/70 dark:bg-gray-800/50 border-t border-gray-100/80 dark:border-gray-700/80"
                    >
                      <td className="py-2 px-5 sticky left-0 z-10 bg-gray-50 dark:bg-gray-800 border-r border-gray-100 dark:border-gray-700">
                        <div className="flex items-center gap-2 pl-6">
                          <span className="text-gray-300 dark:text-gray-600">·</span>
                          <p className="text-xs font-medium text-gray-600 dark:text-gray-400">
                            {sub.account_name}
                          </p>
                        </div>
                      </td>
                      <td className="py-2 px-4 text-right text-xs text-gray-500 dark:text-gray-400">
                        {sub.qty.toLocaleString()}
                      </td>
                      <td className="py-2 px-4 text-right text-xs text-gray-400 dark:text-gray-500">
                        {sub.avg_price.toLocaleString()}
                      </td>
                      <td className="py-2 px-4 text-right text-xs text-gray-500 dark:text-gray-400">
                        {sub.current_price.toLocaleString()}
                      </td>
                      <td className="py-2 px-4 text-right text-xs text-gray-600 dark:text-gray-400">
                        {fmtKrwShort(sub.value_krw)}원
                      </td>
                      <td className={`py-2 px-4 text-right text-xs ${pnlColor(sub.pnl)}`}>
                        <div>
                          {sub.pnl >= 0 ? "+" : ""}
                          {fmtKrwShort(sub.pnl)}원
                        </div>
                        <div className="font-medium">{fmtPct(sub.pnl_pct)}</div>
                      </td>
                      <td className="py-2 px-4" />
                      <td className="py-2 px-4" />
                      <td className="py-2 px-3" />
                    </tr>
                  ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
