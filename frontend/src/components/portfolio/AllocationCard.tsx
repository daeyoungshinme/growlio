import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChartPie } from "lucide-react";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import SkeletonCard from "@/components/common/SkeletonCard";
import { fetchIndexExposure } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";
import { useCollapsible } from "@/hooks/useCollapsible";
import type { PortfolioOverview } from "@/types";
import SegmentedControl from "./allocation/SegmentedControl";
import RegionAllocationView, { type RegionBasis } from "./allocation/RegionAllocationView";
import StockAllocationView from "./allocation/StockAllocationView";
import IndexAllocationView from "./allocation/IndexAllocationView";
import { storageGet, storageSet } from "@/utils/safeStorage";
import { pctOf } from "@/utils/format";

type View = "region" | "stock" | "index";

const VIEW_OPTIONS = [
  { value: "region", label: "국내/해외" },
  { value: "stock", label: "종목" },
  { value: "index", label: "지수" },
] as const;

const OPEN_KEY = "growlio:portfolio:allocationOpen";
const VIEW_KEY = "growlio:portfolio:allocationView";

// 모바일은 보유 종목 목록이 첫 화면 가까이 오도록 기본 접힘(사용자가 펼치면 그 상태를 기억)
function isDesktopViewport(): boolean {
  return typeof window.matchMedia !== "function" || window.matchMedia("(min-width: 640px)").matches;
}

function readStoredView(): View {
  const v = storageGet(VIEW_KEY);
  return VIEW_OPTIONS.some((o) => o.value === v) ? (v as View) : "region";
}

interface Props {
  overview: PortfolioOverview;
  accountId?: string | null;
  /** "종목" 보기의 "전체 비중순 보기" — 아래 보유 종목 목록을 비중순으로 정렬하고 그리로 이동 */
  onShowAllStocks?: () => void;
}

/** 자산탭 "비중 분석" — 국내/해외 · 종목 · 지수 비중을 한 카드에서 같은 막대 형식으로 전환해 본다. */
export default function AllocationCard({ overview, accountId, onShowAllStocks }: Props) {
  const [isOpen, toggleOpen] = useCollapsible(isDesktopViewport, OPEN_KEY);
  const [view, setViewState] = useState<View>(readStoredView);
  const [regionBasis, setRegionBasis] = useState<RegionBasis>("exposure");

  const setView = (next: View) => {
    setViewState(next);
    storageSet(VIEW_KEY, next);
  };

  // 지수 분류 결과는 "지수" 탭과 "실제 투자지역" 기준에서만 필요 — 다른 뷰에선 ETF 프로필 조회를 하지 않는다.
  const needsExposure = view === "index" || (view === "region" && regionBasis === "exposure");
  const exposure = useQuery({
    queryKey: QUERY_KEYS.indexExposure(accountId),
    queryFn: () => fetchIndexExposure(accountId),
    staleTime: STALE_TIME.MEDIUM,
    enabled: isOpen && needsExposure,
  });

  const exposureFallback = exposure.isError ? (
    <div className="flex items-center justify-between gap-2 text-sm text-gray-500 dark:text-gray-400">
      <span>비중 정보를 불러오지 못했어요</span>
      <button
        type="button"
        onClick={() => exposure.refetch()}
        className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} px-3 text-xs border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors`}
      >
        다시 시도
      </button>
    </div>
  ) : (
    <SkeletonCard rows={3} height="h-6" />
  );

  const regionAmounts =
    regionBasis === "listing"
      ? { domestic: overview.domestic_stock_krw ?? 0, overseas: overview.foreign_stock_krw ?? 0 }
      : exposure.data
        ? {
            domestic: exposure.data.region_exposure.domestic_krw,
            overseas: exposure.data.region_exposure.overseas_krw,
            unknown: exposure.data.region_exposure.unknown_krw,
          }
        : null;

  const topStock = overview.stock_allocation.find((a) => a.ticker !== "ETC");
  const listedTotal = (overview.domestic_stock_krw ?? 0) + (overview.foreign_stock_krw ?? 0);
  const collapsedHint = [
    topStock && `최대 종목 ${topStock.name} ${topStock.pct.toFixed(1)}%`,
    // 해외 보유가 없으면 "해외상장 0%"는 정보가 없어 생략
    listedTotal > 0 &&
      (overview.foreign_stock_krw ?? 0) > 0 &&
      `해외상장 ${pctOf(overview.foreign_stock_krw ?? 0, listedTotal).toFixed(0)}%`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <CollapsibleCard
      icon={ChartPie}
      iconWrapClassName="bg-indigo-50 dark:bg-indigo-950"
      iconColorClassName="text-indigo-500 dark:text-indigo-400"
      title="비중 분석"
      isOpen={isOpen}
      onToggle={toggleOpen}
      collapsedHint={collapsedHint || undefined}
    >
      <SegmentedControl
        options={VIEW_OPTIONS}
        value={view}
        onChange={setView}
        ariaLabel="비중 보기"
        stretch
      />
      <div className="mt-4">
        {view === "region" && (
          <RegionAllocationView
            basis={regionBasis}
            onBasisChange={setRegionBasis}
            amounts={regionAmounts}
            fallback={exposureFallback}
          />
        )}
        {view === "stock" && (
          <StockAllocationView items={overview.stock_allocation} onShowAll={onShowAllStocks} />
        )}
        {view === "index" &&
          (exposure.data ? <IndexAllocationView data={exposure.data} /> : exposureFallback)}
      </div>
    </CollapsibleCard>
  );
}
