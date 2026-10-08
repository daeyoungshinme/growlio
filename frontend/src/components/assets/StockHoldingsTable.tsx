import {
  Fragment,
  memo,
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronDown, ChevronRight, Search, X } from "lucide-react";
import { clampPct, fmtKrwShort } from "@/utils/format";
import { groupPositionsByTicker } from "@/utils/portfolio";
import { pnlColor } from "@/utils/colors";
import { weightBarColor } from "@/utils/dividendUtils";
import type { PortfolioPosition, DividendYield } from "@/types";
import EmptyState from "@/components/common/EmptyState";
import { INPUT_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";

const MOBILE_CARD_VIRTUALIZE_THRESHOLD = 10;
const MOBILE_CARD_HEIGHT = 96; // 접힌 카드 추정 높이 (px) — 실제 높이는 measureElement로 실측
const DOMESTIC_DIVIDEND_MARKETS = ["KOSPI", "KOSDAQ", "KRX"];

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

type Agg = ReturnType<typeof groupPositionsByTicker>[number];

/** 보유수량 기준 예상 연배당 — 국내는 원, 해외는 달러 단위(dps 원통화) 그대로 표시. */
function annualDividendLabel(divData: DividendYield, qty: number): string | null {
  if (divData.dps <= 0) return null;
  const total = divData.dps * qty;
  return DOMESTIC_DIVIDEND_MARKETS.includes(divData.market)
    ? `${Math.round(total).toLocaleString()}원`
    : `$${total.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

/** 배당월 칩 — 12개월이면 "월배당" 하나로, 수동 지정 월은 파란 톤으로 구분한다. */
function DividendMonthsChips({ divData }: { divData: DividendYield }) {
  const chipTone = divData.dividend_months_is_manual
    ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
    : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400";
  if (divData.dividend_months.length === 12) {
    return <span className={`text-xs px-2 py-0.5 rounded-full ${chipTone}`}>월배당</span>;
  }
  if (divData.dividend_months.length === 0) {
    return <span className="text-gray-300 dark:text-gray-600">—</span>;
  }
  return (
    <div className="flex flex-wrap gap-0.5 justify-end">
      {divData.dividend_months.map((m) => (
        <span key={m} className={`text-xs px-1.5 py-0.5 rounded-full ${chipTone}`}>
          {m}
        </span>
      ))}
    </div>
  );
}

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

interface MobileCardProps {
  agg: Agg;
  divData: DividendYield | undefined;
  divLoading: boolean;
  divError: boolean;
  expanded: boolean;
  onToggle: () => void;
}

function StockHoldingMobileCard({
  agg,
  divData,
  divLoading,
  divError,
  expanded,
  onToggle,
}: MobileCardProps) {
  const divReady = !divLoading && !divError && divData;
  const annualDiv = divReady ? annualDividendLabel(divData, agg.total_qty) : null;
  return (
    <>
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
            {agg.ticker} · {agg.market} · {agg.total_qty.toLocaleString()}주
          </p>
          <p className={`shrink-0 font-medium tabular-nums ${pnlColor(agg.total_pnl)}`}>
            {agg.total_pnl >= 0 ? "+" : ""}
            {fmtKrwShort(agg.total_pnl)}원 · {agg.pnl_pct >= 0 ? "+" : ""}
            {agg.pnl_pct.toFixed(2)}%
          </p>
        </div>
        <div className="mt-2 flex items-center gap-2 text-xs">
          <div className="flex-1 h-1.5 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
            <div
              className={`h-full rounded-full ${weightBarColor(agg.weight_in_stock)}`}
              style={{ width: `${clampPct(agg.weight_in_stock)}%` }}
            />
          </div>
          {/* 고정 폭 — 라벨 길이에 따라 막대 끝이 들쭉날쭉하지 않게 */}
          <span className="shrink-0 w-[4.75rem] text-right text-gray-500 dark:text-gray-400 tabular-nums">
            비중 {agg.weight_in_stock.toFixed(1)}%
          </span>
          {divReady && divData.investment_yield > 0 && (
            <span className="shrink-0 text-green-600 dark:text-green-500 tabular-nums">
              배당 {divData.investment_yield.toFixed(2)}%
            </span>
          )}
          <ChevronDown
            size={14}
            aria-hidden="true"
            className={`shrink-0 text-gray-400 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
          />
        </div>
      </button>
      {expanded && (
        <div className="mt-3 rounded-lg bg-gray-50 dark:bg-gray-800 px-3 py-2.5 text-xs">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5">
            <DetailItem label="평단가">
              {Math.round(agg.weighted_avg_price).toLocaleString()}
            </DetailItem>
            <DetailItem label="현재가">{agg.current_price.toLocaleString()}</DetailItem>
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
                    <span className={`ml-1.5 ${pnlColor(sub.pnl)}`}>
                      {sub.pnl_pct >= 0 ? "+" : ""}
                      {sub.pnl_pct.toFixed(2)}%
                    </span>
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

interface Props {
  positions: PortfolioPosition[];
  dividendMap: Record<string, DividendYield>;
  divLoading: boolean;
  divError: boolean;
}

const MOBILE_SORT_OPTIONS: { key: AggSortKey; label: string }[] = [
  { key: "total_value_krw", label: "평가금액순" },
  { key: "pnl_pct", label: "수익률순" },
  { key: "total_pnl", label: "손익순" },
  { key: "weight_in_stock", label: "비중순" },
];

function StockHoldingsTable({ positions, dividendMap, divLoading, divError }: Props) {
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

  // 모바일 목록은 별도 스크롤 박스 없이 페이지(AppLayout의 <main>) 스크롤을 그대로 따라 가상화한다.
  // 내부 스크롤 박스(70vh)는 페이지 스크롤이 목록에 갇히고 pull-to-refresh와 겹쳤다.
  const mobileContainerRef = useRef<HTMLDivElement>(null);
  const [scrollEl, setScrollEl] = useState<HTMLElement | null>(null);
  const [scrollMargin, setScrollMargin] = useState(0);
  const wantsVirtualMobile = sorted.length >= MOBILE_CARD_VIRTUALIZE_THRESHOLD;
  useLayoutEffect(() => {
    const list = mobileContainerRef.current;
    const main = list?.closest("main") ?? null;
    if (!wantsVirtualMobile || !list || !main) {
      setScrollEl(null);
      return;
    }
    const measure = () => {
      // sm 이상에선 모바일 목록이 display:none(offsetParent null) — 데스크톱 스크롤마다 리렌더하지 않도록 끈다
      setScrollEl(list.offsetParent ? main : null);
      setScrollMargin(
        list.getBoundingClientRect().top - main.getBoundingClientRect().top + main.scrollTop,
      );
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    // 위쪽 카드(비중 분석 접기 등) 높이가 바뀌면 목록 시작 위치도 바뀌므로 다시 잰다
    const observer = new ResizeObserver(measure);
    observer.observe(main.firstElementChild ?? main);
    return () => observer.disconnect();
  }, [wantsVirtualMobile]);
  const useVirtualMobile = wantsVirtualMobile && scrollEl !== null;
  // eslint-disable-next-line react-hooks/incompatible-library
  const mobileVirtualizer = useVirtualizer({
    count: sorted.length,
    getScrollElement: () => scrollEl,
    estimateSize: () => MOBILE_CARD_HEIGHT,
    overscan: 5,
    scrollMargin,
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
        {/* 총 평가액은 바로 위 "주식 총평가액" 요약 카드와 같은 값이라 종목 수만 표시(U3) */}
        <span className="text-xs text-gray-400 dark:text-gray-500">{aggregated.length}종목</span>
      </div>
      {aggregated.length === 0 ? (
        <EmptyState title="보유 종목이 없습니다" compact />
      ) : (
        <>
          <div className="px-5 py-3 border-b border-gray-100 dark:border-gray-700 flex gap-2">
            <div className="relative flex-1 min-w-0">
              <Search
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500"
              />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="종목·티커 검색"
                aria-label="종목명 또는 티커 검색"
                className={`${INPUT_SM} w-full pl-8 pr-10`}
              />
              {query && (
                <button
                  onClick={() => setQuery("")}
                  aria-label="검색어 지우기"
                  className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} absolute right-0 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded`}
                >
                  <X size={14} />
                </button>
              )}
            </div>
            {/* 데스크톱은 테이블 헤더(SortTh)로 정렬 — 모바일 카드 뷰엔 헤더가 없어 정렬 수단이 없었음(U5b) */}
            <select
              value={sort.key}
              onChange={(e) => setSort({ key: e.target.value as AggSortKey, dir: "desc" })}
              aria-label="보유 종목 정렬"
              className={`${INPUT_SM} w-auto shrink-0 sm:hidden`}
            >
              {MOBILE_SORT_OPTIONS.map((o) => (
                <option key={o.key} value={o.key}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          {filtered.length === 0 ? (
            <EmptyState title="검색 결과가 없습니다" compact />
          ) : (
            <>
              {/* 모바일 카드 뷰 — 탭하면 평단가·현재가·배당월·계좌별 보유가 펼쳐진다 */}
              <div
                ref={mobileContainerRef}
                className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700"
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
                          ref={mobileVirtualizer.measureElement}
                          data-index={virtualItem.index}
                          style={{
                            position: "absolute",
                            top: 0,
                            left: 0,
                            width: "100%",
                            transform: `translateY(${virtualItem.start - scrollMargin}px)`,
                          }}
                          className="px-4 py-3 border-b border-gray-100 dark:border-gray-700"
                        >
                          <StockHoldingMobileCard
                            agg={agg}
                            divData={dividendMap[key]}
                            divLoading={divLoading}
                            divError={divError}
                            expanded={expandedSet.has(key)}
                            onToggle={() => toggle(key)}
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
                          expanded={expandedSet.has(key)}
                          onToggle={() => toggle(key)}
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
                      const annualDiv = divData
                        ? annualDividendLabel(divData, agg.total_qty)
                        : null;
                      return (
                        <Fragment key={key}>
                          <tr
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
                                      {annualDiv && (
                                        <p className="text-xs text-gray-400 mt-0.5">{annualDiv}</p>
                                      )}
                                    </>
                                  ) : (
                                    <span className="text-gray-300">—</span>
                                  )}
                                </td>
                                <td className="py-3 px-3 text-right">
                                  <DividendMonthsChips divData={divData} />
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
                        </Fragment>
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
