import { useMemo, type ComponentProps, type ReactNode } from "react";
import { RefreshCw } from "lucide-react";
import type { GoalRecommendationItem, SuggestedGoalCandidate } from "@/api/rebalancing";
import type { MarketRiskLevel } from "@/api/marketSignals";
import type { RecommendationDrift } from "@/utils/recommendationDrift";
import MarketSignalLevelBadge from "@/components/rebalancing/MarketSignalLevelBadge";
import RecommendationApplySection from "@/components/rebalancing/RecommendationApplySection";
import RecommendationWeightList from "@/components/rebalancing/RecommendationWeightList";
import SuggestedCandidatesBlock from "@/components/rebalancing/SuggestedCandidatesBlock";
import OverlapGroupsBlock from "@/components/rebalancing/OverlapGroupsBlock";
import { useCandidateOverlap } from "@/hooks/useCandidateOverlap";
import {
  buildTerMap,
  formatTerPct,
  groupsTouchingItems,
  itemKey,
  weightedTerPct,
} from "@/utils/etfOverlap";
import PortfolioWeightChart from "@/components/portfolio-analysis/PortfolioWeightChart";

function driftBadgeLabel(drift: RecommendationDrift): string {
  const parts: string[] = [];
  if (drift.maxDeltaPct > 0) parts.push(`최대 ${drift.maxDeltaPct}%p 차이`);
  if (drift.newCandidateCount > 0) parts.push(`신규 후보 ${drift.newCandidateCount}개`);
  return `시장 상황이 바뀌어 추천 비중이 달라졌어요 · ${parts.join(" · ")}`;
}

interface Props {
  drift: RecommendationDrift | null;
  items: GoalRecommendationItem[];
  note?: string | null;
  marketSignalLevel?: MarketRiskLevel | null;
  suggestedCandidates: SuggestedGoalCandidate[];
  onAddSuggested: () => void;
  addPending: boolean;
  /** 비중 목록 바로 아래, 안내문구 위에 추가로 보여줄 내용(연령대 탭의 현금성 자산 합성 안내 등). */
  extraNoticeAfterWeightList?: ReactNode;
  /** 적용 섹션 위에 추가로 보여줄 안내(기간별 탭의 현금성 자산 매칭 안내 등). */
  extraNoticeBeforeApply?: ReactNode;
  /** null이면 적용 섹션 자체를 렌더하지 않는다(예: 기간별 탭에서 현금성 자산을 자동 연결할
   * 계좌가 없어 적용이 불가능한 경우 — `extraNoticeBeforeApply`의 안내문구만 노출). */
  applySection: ComponentProps<typeof RecommendationApplySection> | null;
}

/** 전체/연령대/기간별 3개 탭이 공유하는 추천 결과 렌더링 — 드리프트 배지 → 비중 목록(+총보수) →
 * 평균 보수 → 안내문구(+시장신호 배지) → 중복 투자 점검 → 미등록 후보 제안 → 적용 섹션 순서를
 * 한 곳에서 조립한다. 총보수·중복 정보는 저장된 후보 목록 기준 쿼리 하나를 3개 탭이 공유한다. */
export default function RecommendationResultPanel({
  drift,
  items,
  note,
  marketSignalLevel,
  suggestedCandidates,
  onAddSuggested,
  addPending,
  extraNoticeAfterWeightList,
  extraNoticeBeforeApply,
  applySection,
}: Props) {
  const { data: overlap } = useCandidateOverlap();
  const terMap = useMemo(() => buildTerMap(overlap), [overlap]);
  const avgTer = weightedTerPct(items, terMap);
  const overlapGroups = useMemo(
    () => groupsTouchingItems(overlap?.groups ?? [], items),
    [overlap, items],
  );
  const weightByKey = useMemo(
    () => new Map(items.map((i) => [itemKey(i.ticker, i.market), i.weight])),
    [items],
  );

  return (
    <>
      {drift && (
        <p className="text-xs text-amber-600 dark:text-amber-500 flex items-center gap-1.5">
          <RefreshCw size={12} className="shrink-0" />
          {driftBadgeLabel(drift)}
        </p>
      )}

      <RecommendationWeightList items={items} terMap={terMap} />

      {avgTer && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          평균 총보수 연 {formatTerPct(avgTer.pct)}
          {avgTer.coveragePct < 99.5 &&
            ` (보수 확인된 비중 ${avgTer.coveragePct.toFixed(0)}% 기준)`}
        </p>
      )}

      <PortfolioWeightChart items={items} />

      {extraNoticeAfterWeightList}

      {note && (
        <p className="text-xs text-amber-600 dark:text-amber-500 pt-1 flex items-center gap-1.5 flex-wrap">
          {(marketSignalLevel === "YELLOW" || marketSignalLevel === "RED") && (
            <MarketSignalLevelBadge level={marketSignalLevel} />
          )}
          {note}
        </p>
      )}

      <OverlapGroupsBlock groups={overlapGroups} weightByKey={weightByKey} />

      <SuggestedCandidatesBlock
        candidates={suggestedCandidates}
        onAdd={onAddSuggested}
        isPending={addPending}
      />

      <p className="text-xs text-teal-500 dark:text-teal-500 pt-1">
        등록한 후보 종목 기준 참고용 제안 — 자동 반영되지 않습니다.
      </p>

      {extraNoticeBeforeApply}

      {applySection && <RecommendationApplySection {...applySection} />}
    </>
  );
}
