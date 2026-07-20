import { memo, useCallback, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronDown, ChevronRight, Search, X } from "lucide-react";
import { fmtKrwShort } from "@/utils/format";
import { groupPositionsByTicker } from "@/utils/portfolio";
import { pnlColor } from "@/utils/colors";
import type { PortfolioPosition, DividendYield } from "@/types";
import EmptyState from "@/components/common/EmptyState";
import { INPUT_SM } from "@/constants/inputStyles";

const MOBILE_CARD_VIRTUALIZE_THRESHOLD = 10;
const MOBILE_CARD_HEIGHT = 80; // 카드 평균 높이 (px)

type AggSortKey = "total_value_krw" | "pnl_pct" | "total_pnl" | "weight_in_stock";
type SortDir = "asc" | "desc";
interface SortState {
  key: AggSortKey;
  dir: SortDir;
}

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

interface MobileCardProps {
  agg: ReturnType<typeof groupPositionsByTicker>[number];
  divData: DividendYield | undefined;
  divLoading: boolean;
  divError: boolean;
}

function StockHoldingMobileCard({ agg, divData, divLoading, divError }: MobileCardProps) {
  return (
    <>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-sm text-gray-900 dark:text-gray-50 truncate">
            {agg.name}
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            {agg.ticker} · {agg.market}
          </p>
        </div>
        <div className="text-right shrink-0">
          <p className="font-semibold text-gray-900 dark:text-gray-50 text-sm">
            {fmtKrwShort(agg.total_value_krw)}원
          </p>
          <p className={`text-xs font-medium ${pnlColor(agg.total_pnl)}`}>
            {agg.total_pnl >= 0 ? "+" : ""}
            {fmtKrwShort(agg.total_pnl)}원 ({agg.pnl_pct >= 0 ? "+" : ""}
            {agg.pnl_pct.toFixed(2)}%)
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2 mt-2 text-xs text-gray-400 dark:text-gray-500 flex-wrap">
        <span>{agg.total_qty.toLocaleString()}주</span>
        <span>·</span>
        <span className="text-indigo-500 dark:text-indigo-400">
          비중 {agg.weight_in_stock.toFixed(1)}%
        </span>
        {!divLoading && !divError && divData && divData.investment_yield > 0 && (
          <>
            <span>·</span>
            <span className="text-green-600 dark:text-green-500">
              배당 {divData.investment_yield.toFixed(2)}%
            </span>
          </>
        )}
      </div>
    </>
  );
}

interface Props {
  positions: PortfolioPosition[];
  totalStock: number;
  dividendMap: Record<string, DividendYield>;
  divLoading: boolean;
  divError: boolean;
}

function StockHoldingsTable({ positions, totalStock, dividendMap, divLoading, divError }: Props) {
  const [sort, setSort] = useState<SortState>({ key: "total_value_krw", dir: "desc" });
  const [expandedSet, setExpandedSet] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");

  const handleSort = useCallback((k: AggSortKey) => {
    setSort((prev) =>
      prev.key === k
        ? { key: k, dir: prev.dir === "desc" ? "asc" : "desc" }
        : { key: k, dir: "desc" },
    );
  }, []);

  const aggregated = useMemo(() => groupPositionsByTicker(positions), [positions]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return aggregated;
    return aggregated.filter(
      (agg) => agg.name.toLowerCase().includes(q) || agg.ticker.toLowerCase().includes(q),
    );
  }, [aggregated, query]);
  const sorted = useMemo(() => {
    const sign = sort.dir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => (a[sort.key] - b[sort.key]) * sign);
  }, [filtered, sort]);

  const mobileContainerRef = useRef<HTMLDivElement>(null);
  const useVirtualMobile = sorted.length >= MOBILE_CARD_VIRTUALIZE_THRESHOLD;
  const getMobileScrollElement = useCallback(() => mobileContainerRef.current, []);
  // eslint-disable-next-line react-hooks/incompatible-library
  const mobileVirtualizer = useVirtualizer({
    count: sorted.length,
    getScrollElement: getMobileScrollElement,
    estimateSize: () => MOBILE_CARD_HEIGHT,
    overscan: 5,
    enabled: useVirtualMobile,
  });

  const toggle = (key: string) => {
    setExpandedSet((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div className="card-overflow">
      <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
        <h3 className="font-semibold text-gray-800 dark:text-gray-200">전체 보유 종목</h3>
        <span className="text-xs text-gray-400 dark:text-gray-500">
          {aggregated.length}종목 · 총 {fmtKrwShort(totalStock)}원
        </span>
      </div>
      {aggregated.length === 0 ? (
        <EmptyState title="보유 종목이 없습니다" compact />
      ) : (
        <>
          <div className="px-5 py-3 border-b border-gray-100 dark:border-gray-700">
            <div className="relative">
              <Search
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500"
              />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="종목명 또는 티커 검색"
                className={`${INPUT_SM} pl-8 pr-8`}
              />
              {query && (
                <button
                  onClick={() => setQuery("")}
                  aria-label="검색어 지우기"
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded"
                >
                  <X size={14} />
                </button>
              )}
            </div>
          </div>
          {filtered.length === 0 ? (
            <EmptyState title="검색 결과가 없습니다" compact />
          ) : (
            <>
              {/* 모바일 카드 뷰 */}
              <div
                ref={mobileContainerRef}
                className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700"
                style={useVirtualMobile ? { maxHeight: "70vh", overflowY: "auto" } : undefined}
              >
                {useVirtualMobile ? (
                  <div
                    style={{
                      height: `${mobileVirtualizer.getTotalSize()}px`,
                      position: "relative",
                    }}
                  >
                    {mobileVirtualizer.getVirtualItems().map((virtualItem) => {
                      const agg = sorted[virtualItem.index];
                      const key = `${agg.ticker}-${agg.market}`;
                      return (
                        <div
                          key={key}
                          style={{
                            position: "absolute",
                            top: 0,
                            left: 0,
                            width: "100%",
                            transform: `translateY(${virtualItem.start}px)`,
                          }}
                          className="px-4 py-3 border-b border-gray-100 dark:border-gray-700"
                        >
                          <StockHoldingMobileCard
                            agg={agg}
                            divData={dividendMap[key]}
                            divLoading={divLoading}
                            divError={divError}
                          />
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  sorted.map((agg) => {
                    const key = `${agg.ticker}-${agg.market}`;
                    return (
                      <div key={key} className="px-4 py-3">
                        <StockHoldingMobileCard
                          agg={agg}
                          divData={dividendMap[key]}
                          divLoading={divLoading}
                          divError={divError}
                        />
                      </div>
                    );
                  })
                )}
              </div>

              {/* 데스크탑 테이블 */}
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
                      <th
                        scope="col"
                        className="py-2.5 px-4 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase"
                      >
                        수량
                      </th>
                      <th
                        scope="col"
                        className="py-2.5 px-4 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase"
                      >
                        평단가
                      </th>
                      <th
                        scope="col"
                        className="py-2.5 px-4 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase"
                      >
                        현재가
                      </th>
                      <SortTh
                        k="total_value_krw"
                        label="평가금액"
                        className="min-w-[120px]"
                        sort={sort}
                        onSort={handleSort}
                      />
                      <SortTh k="pnl_pct" label="수익" sort={sort} onSort={handleSort} />
                      <SortTh k="weight_in_stock" label="비중" sort={sort} onSort={handleSort} />
                      <th
                        scope="col"
                        className="py-2.5 px-4 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase min-w-[130px]"
                      >
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
                    {sorted.map((agg) => {
                      const key = `${agg.ticker}-${agg.market}`;
                      const isExpanded = expandedSet.has(key);
                      const hasMultiple = agg.sub_positions.length > 1;
                      const divData = dividendMap[key];
                      return (
                        <>
                          <tr
                            key={key}
                            className={`border-t border-gray-100 dark:border-gray-700 cursor-pointer ${
                              isExpanded
                                ? "bg-blue-50/30 dark:bg-blue-950/20"
                                : "hover:bg-blue-50/20 dark:hover:bg-blue-950/10"
                            }`}
                            onClick={() => toggle(key)}
                          >
                            <td className="py-3 px-5 sticky left-0 z-10 bg-white dark:bg-gray-900 border-r border-gray-100 dark:border-gray-700">
                              <div className="flex items-center gap-2">
                                <span
                                  className={`text-gray-400 dark:text-gray-500 ${hasMultiple ? "visible" : "invisible"}`}
                                >
                                  {isExpanded ? (
                                    <ChevronDown size={14} />
                                  ) : (
                                    <ChevronRight size={14} />
                                  )}
                                </span>
                                <div>
                                  <p className="font-semibold text-sm text-gray-900 dark:text-gray-50">
                                    {agg.name}
                                  </p>
                                  <p className="text-xs text-gray-400 dark:text-gray-500">
                                    {agg.ticker} · {agg.market}
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
                              <span className="font-bold">
                                ({agg.pnl_pct >= 0 ? "+" : ""}
                                {agg.pnl_pct.toFixed(2)}%)
                              </span>
                            </td>
                            <td className="py-3 px-4 text-right">
                              <div className="flex items-center justify-end gap-1.5">
                                <div className="w-16 bg-gray-100 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                                  <div
                                    className="bg-blue-500 h-full rounded-full"
                                    style={{ width: `${Math.min(agg.weight_in_stock, 100)}%` }}
                                  />
                                </div>
                                <span className="text-xs text-indigo-500 dark:text-indigo-400 w-10 text-right">
                                  {agg.weight_in_stock.toFixed(1)}%
                                </span>
                              </div>
                            </td>
                            {divLoading ? (
                              <>
                                <td className="py-3 px-4 text-right text-gray-300 text-xs">...</td>
                                <td className="py-3 px-4 text-right text-gray-300 text-xs">...</td>
                              </>
                            ) : divError ? (
                              <>
                                <td className="py-3 px-4 text-right text-xs text-red-400">오류</td>
                                <td className="py-3 px-4 text-right text-gray-300">—</td>
                              </>
                            ) : divData ? (
                              <>
                                <td className="py-3 px-4 text-right">
                                  {divData.investment_yield > 0 ? (
                                    <>
                                      <span className="text-xs text-green-600 dark:text-green-400 font-medium">
                                        {divData.investment_yield.toFixed(2)}%
                                      </span>
                                      {divData.dps > 0 && (
                                        <p className="text-xs text-gray-400 mt-0.5">
                                          {(divData.dps * agg.total_qty).toLocaleString()}
                                          {["KOSPI", "KOSDAQ", "KRX"].includes(divData.market)
                                            ? "원"
                                            : "$"}
                                        </p>
                                      )}
                                    </>
                                  ) : (
                                    <span className="text-gray-300">—</span>
                                  )}
                                </td>
                                <td className="py-3 px-3 text-right">
                                  {divData.dividend_months.length === 12 ? (
                                    <span
                                      className={`text-xs px-2 py-0.5 rounded-full ${
                                        divData.dividend_months_is_manual
                                          ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
                                          : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
                                      }`}
                                    >
                                      월배당
                                    </span>
                                  ) : divData.dividend_months.length > 0 ? (
                                    <div className="flex flex-wrap gap-0.5 justify-end">
                                      {divData.dividend_months.map((m) => (
                                        <span
                                          key={m}
                                          className={`text-xs px-1.5 py-0.5 rounded-full ${
                                            divData.dividend_months_is_manual
                                              ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
                                              : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
                                          }`}
                                        >
                                          {m}
                                        </span>
                                      ))}
                                    </div>
                                  ) : (
                                    <span className="text-gray-300 dark:text-gray-600">—</span>
                                  )}
                                </td>
                              </>
                            ) : (
                              <>
                                <td className="py-3 px-4 text-right text-gray-300 dark:text-gray-600">
                                  —
                                </td>
                                <td className="py-3 px-4 text-right text-gray-300 dark:text-gray-600">
                                  —
                                </td>
                              </>
                            )}
                          </tr>

                          {isExpanded &&
                            hasMultiple &&
                            agg.sub_positions.map((sub) => (
                              <tr
                                key={`${sub.account_id}-${sub.ticker}`}
                                className="bg-gray-50/70 dark:bg-gray-800/50 border-t border-gray-100/80 dark:border-gray-700/80"
                              >
                                <td className="py-2 px-4" />
                                <td className="py-2 px-5">
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
                                  <div className="font-medium">
                                    {sub.pnl_pct >= 0 ? "+" : ""}
                                    {sub.pnl_pct.toFixed(2)}%
                                  </div>
                                </td>
                                <td className="py-2 px-4" />
                                <td className="py-2 px-4" />
                              </tr>
                            ))}
                        </>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

export default memo(StockHoldingsTable);
