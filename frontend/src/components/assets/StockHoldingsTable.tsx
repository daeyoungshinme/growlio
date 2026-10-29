import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useIsSmUp } from "@/hooks/useMediaQuery";
import { Search, X } from "lucide-react";
import { groupPositionsByTicker } from "@/utils/portfolio";
import type { PortfolioPosition, DividendYield } from "@/types";
import EmptyState from "@/components/common/EmptyState";
import { INPUT_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import StockHoldingMobileCard from "./stockHoldings/StockHoldingMobileCard";
import StockHoldingsDesktopTable from "./stockHoldings/StockHoldingsDesktopTable";
import { holdingKey, type AggSortKey, type SortState } from "./stockHoldings/holdings";

const MOBILE_CARD_VIRTUALIZE_THRESHOLD = 10;
const MOBILE_CARD_HEIGHT = 64; // 접힌 카드(2줄) 추정 높이 (px) — 실제 높이는 measureElement로 실측

/** 바깥(비중 분석 카드 "전체 비중순 보기")에서 정렬을 바꿔 달라는 요청 — nonce가 바뀔 때마다 적용 */
export interface HoldingsSortRequest {
  key: AggSortKey;
  nonce: number;
}

interface Props {
  positions: PortfolioPosition[];
  dividendMap: Record<string, DividendYield>;
  divLoading: boolean;
  divError: boolean;
  sortRequest?: HoldingsSortRequest | null;
}

const MOBILE_SORT_OPTIONS: { key: AggSortKey; label: string }[] = [
  // 360px에서 검색 placeholder가 잘리지 않도록 짧게 — 기준은 평가금액
  { key: "total_value_krw", label: "금액순" },
  { key: "pnl_pct", label: "수익률순" },
  { key: "total_pnl", label: "손익순" },
  { key: "weight_in_stock", label: "비중순" },
];

function StockHoldingsTable({ positions, dividendMap, divLoading, divError, sortRequest }: Props) {
  const [sort, setSort] = useState<SortState>({ key: "total_value_krw", dir: "desc" });
  // 데스크톱 표는 여러 행을 펼치고, 모바일 카드는 한 장만 펼친다 — 상태를 나눠 뷰포트 전환 시 규칙이 섞이지 않게 한다
  const [expandedSet, setExpandedSet] = useState<Set<string>>(new Set());
  const [expandedCard, setExpandedCard] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  // 요청은 페이지 상태라 탭을 오가며 재마운트되면 같은 요청이 다시 들어온다 — 마운트 시점 nonce는 이미 적용된 것으로 본다
  const appliedNonceRef = useRef(sortRequest?.nonce);
  useEffect(() => {
    if (!sortRequest || sortRequest.nonce === appliedNonceRef.current) return;
    appliedNonceRef.current = sortRequest.nonce;
    setSort({ key: sortRequest.key, dir: "desc" });
    setQuery("");
    setExpandedSet(new Set());
    setExpandedCard(null);
  }, [sortRequest]);

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
  // 실제로 보이는 쪽만 렌더(null = 판정 불가 → 둘 다 렌더하고 CSS에 맡김)
  const isSmUp = useIsSmUp();
  const showMobile = isSmUp !== true;
  const showDesktop = isSmUp !== false;
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
  // 모바일은 한 번에 한 카드만 펼친다 — 여러 장 펼친 채 내려가면 목록이 끝없이 길어진다
  const toggleSingle = (key: string) => {
    setExpandedCard((prev) => (prev === key ? null : key));
  };

  return (
    // 모바일은 검색·정렬 바를 sticky로 두려고 overflow-hidden을 푼다(sticky는 overflow 조상이 있으면 그 안에 갇힘)
    <div className="card-overflow max-sm:overflow-visible">
      <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
        <h3 className="font-semibold text-gray-800 dark:text-gray-200">전체 보유 종목</h3>
        {/* 총 평가액은 바로 위 "주식 총평가액" 요약 카드와 같은 값이라 종목 수만 표시(U3) */}
        <span className="text-xs text-gray-400 dark:text-gray-500">{aggregated.length}종목</span>
      </div>
      {aggregated.length === 0 ? (
        <EmptyState title="보유 종목이 없습니다" compact />
      ) : (
        <>
          <div className="px-5 py-3 border-b border-gray-100 dark:border-gray-700 flex gap-2 max-sm:sticky max-sm:-top-4 max-sm:z-10 bg-white dark:bg-gray-900">
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
                // 지우기 버튼 자리는 검색어가 있을 때만 비운다
                className={`${INPUT_SM} w-full pl-8 ${query ? "pr-10" : "pr-3"}`}
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
              {showMobile && (
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
                        const key = holdingKey(agg);
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
                            className="px-4 py-2.5 border-b border-gray-100 dark:border-gray-700"
                          >
                            <StockHoldingMobileCard
                              agg={agg}
                              divData={dividendMap[key]}
                              divLoading={divLoading}
                              divError={divError}
                              expanded={expandedCard === key}
                              onToggle={() => toggleSingle(key)}
                            />
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    sorted.map((agg) => {
                      const key = holdingKey(agg);
                      return (
                        <div key={key} className="px-4 py-2.5">
                          <StockHoldingMobileCard
                            agg={agg}
                            divData={dividendMap[key]}
                            divLoading={divLoading}
                            divError={divError}
                            expanded={expandedCard === key}
                            onToggle={() => toggleSingle(key)}
                          />
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* 데스크탑 테이블 — 모바일에선 숨겨져 있어도 전 종목 행을 렌더하던 것을 막는다 */}
              {showDesktop && (
                <StockHoldingsDesktopTable
                  rows={sorted}
                  sort={sort}
                  onSort={handleSort}
                  expanded={expandedSet}
                  onToggle={toggle}
                  dividendMap={dividendMap}
                  divLoading={divLoading}
                  divError={divError}
                />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

export default memo(StockHoldingsTable);
