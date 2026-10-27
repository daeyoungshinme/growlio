import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, ChevronRight, ListChecks, RotateCw } from "lucide-react";
import { fetchActionItems, REBALANCE_GROUP_ID, type ActionItem } from "@/api/dashboard";
import type { MarketSignalResponse } from "@/api/marketSignals";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { useCollapsible } from "@/hooks/useCollapsible";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import SkeletonCard from "@/components/common/SkeletonCard";
import { ACTION_PRIORITY_STYLE, deadlineLabel } from "@/utils/actionPriority";
import { MARKET_SIGNAL_BADGE_CLASS, MARKET_SIGNAL_LABEL } from "@/utils/marketSignalBadge";
import { rebalancingUrl } from "@/utils/rebalancingUrl";
import { TOUCH_TARGET_ROW } from "@/constants/uiSizes";
import { driftSummaryQuery } from "@/api/queryOptions";

const VISIBLE_LIMIT = 3;

type MarketSignal = MarketSignalResponse | null | undefined;

// 리밸런싱 탭과 같은 queryKey — 캐시 공유. 묶음 행이 있을 때만 조회한다
function useDriftSummaries() {
  return useQuery(driftSummaryQuery).data;
}

/** 리밸런싱 행 제목 옆 시장 신호 — 이탈을 지금 처리할지 판단할 때 함께 보는 정보라 리밸런싱 행에만 둔다(docs/plans/73) */
function MarketSignalPill({ marketSignal }: { marketSignal: MarketSignal }) {
  if (!marketSignal) return null;
  return (
    <span
      className={`ml-1.5 inline-flex items-center gap-1 align-middle text-xs font-semibold rounded-full px-2 py-0.5 whitespace-nowrap ${MARKET_SIGNAL_BADGE_CLASS[marketSignal.composite_level]}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-80" />
      시장 {MARKET_SIGNAL_LABEL[marketSignal.composite_level]}
    </span>
  );
}

/** 이탈 포트폴리오 2개 이상을 백엔드가 1행으로 묶은 것(docs/plans/73) — 이동 대신 카드 안에서 펼쳐
 * 이탈 포트폴리오만 보여 주고, 각 행이 해당 포트폴리오 탭으로 간다. */
function RebalanceGroupRow({
  item,
  marketSignal,
}: {
  item: ActionItem;
  marketSignal: MarketSignal;
}) {
  const [expanded, toggleExpanded] = useCollapsible(false);
  const driftSummaries = useDriftSummaries();
  const drifted = (driftSummaries ?? [])
    .filter((s) => s.needs_rebalancing)
    .sort((a, b) => b.max_drift_pct - a.max_drift_pct);
  const priority = ACTION_PRIORITY_STYLE[item.priority];
  return (
    <li className="border-b border-gray-100 dark:border-gray-700 last:border-0">
      <button
        onClick={toggleExpanded}
        aria-expanded={expanded}
        className="flex items-start gap-3 w-full min-h-[44px] py-3 text-left active:opacity-70"
      >
        <span
          className={`mt-0.5 shrink-0 text-xs font-semibold rounded-full px-2 py-0.5 ${priority.className}`}
        >
          {priority.label}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            <span>{item.title}</span>
            <MarketSignalPill marketSignal={marketSignal} />
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-relaxed">
            {item.detail}
          </p>
        </div>
        {/* 이동이 아니라 펼침이므로 CTA 문구를 화면에 둔다 */}
        <span className="mt-0.5 shrink-0 inline-flex items-center gap-0.5 text-xs font-medium text-blue-600 dark:text-blue-400">
          {expanded ? "접기" : item.cta_label}
          <ChevronDown
            size={12}
            className={`transition-transform ${expanded ? "rotate-180" : ""}`}
          />
        </span>
      </button>
      {expanded && (
        <ul className="-mt-1 mb-2 ml-3 pl-3 border-l-2 border-red-100 dark:border-red-900/40">
          {drifted.length === 0 ? (
            <li>
              <Link
                to={item.link}
                className={`${TOUCH_TARGET_ROW} gap-1 text-xs font-medium text-blue-600 dark:text-blue-400`}
              >
                리밸런싱 탭에서 보기 <ChevronRight size={12} />
              </Link>
            </li>
          ) : (
            drifted.map((s) => (
              <li key={s.portfolio_id}>
                <Link
                  to={rebalancingUrl({ tab: "포트폴리오", portfolioId: s.portfolio_id })}
                  className="flex items-center gap-2 min-h-[44px] py-1.5 active:opacity-70"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                      {s.portfolio_name}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      최대 {s.max_drift_pct.toFixed(1)}%p · {s.drifted_items_count}종목이 기준{" "}
                      {s.threshold_pct}%p 초과
                    </p>
                  </div>
                  <ChevronRight size={16} className="shrink-0 text-gray-300 dark:text-gray-600" />
                </Link>
              </li>
            ))
          )}
        </ul>
      )}
    </li>
  );
}

function ActionRow({ item, marketSignal }: { item: ActionItem; marketSignal: MarketSignal }) {
  if (item.id === REBALANCE_GROUP_ID)
    return <RebalanceGroupRow item={item} marketSignal={marketSignal} />;
  const priority = ACTION_PRIORITY_STYLE[item.priority];
  return (
    <li>
      <Link
        to={item.link}
        className="flex items-start gap-3 min-h-[44px] py-3 border-b border-gray-100 dark:border-gray-700 last:border-0 active:opacity-70"
      >
        <span
          className={`mt-0.5 shrink-0 text-xs font-semibold rounded-full px-2 py-0.5 ${priority.className}`}
        >
          {priority.label}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            <span>{item.title}</span>
            {item.deadline && (
              <span className="ml-1.5 text-xs font-normal text-gray-500 dark:text-gray-400 whitespace-nowrap">
                {deadlineLabel(item.deadline)}
              </span>
            )}
            {item.kind === "REBALANCE" && <MarketSignalPill marketSignal={marketSignal} />}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-relaxed">
            {item.detail}
          </p>
          {/* 행 전체가 링크이고 chevron이 이동을 알리므로 CTA 문구는 보조기기에만 (docs/plans/67 P1-5) */}
          <span className="sr-only">{item.cta_label}</span>
        </div>
        <ChevronRight size={16} className="mt-0.5 shrink-0 text-gray-300 dark:text-gray-600" />
      </Link>
    </li>
  );
}

interface Props {
  marketSignal?: MarketSignalResponse | null;
}

/** 홈 "지금 할 일" — 전술 제안 비중 적용·리밸런싱 필요·자동매수 예수금 부족·세금 경고·절세 1순위·챌린지 미입금을
 * 우선순위 리스트 1장으로 모은다(docs/plans/50 M5). 집계·정렬은 백엔드 `/dashboard/action-items`.
 * 홈에서 리밸런싱을 다루는 카드는 이것 하나 — 리밸런싱 행에 시장 신호 배지를 붙인다(docs/plans/73). */
export default function ActionItemsCard({ marketSignal }: Props) {
  const [isOpen, toggleOpen] = useCollapsible(true, "growlio:dashboard:actionItemsOpen");
  const [showAll, toggleShowAll] = useCollapsible(false);
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: QUERY_KEYS.actionItems,
    queryFn: fetchActionItems,
    staleTime: STALE_TIME.MEDIUM,
  });

  if (isLoading) return <SkeletonCard rows={2} />;
  // 집계 실패는 홈 전체를 막지 않는다 — 다만 조용히 사라지면 "할 일 없음"으로 오해하므로 한 줄로 알린다
  if (isError) {
    return (
      <div className="card flex items-center gap-2">
        <p className="flex-1 text-sm text-gray-600 dark:text-gray-400">
          지금 할 일을 불러오지 못했어요
        </p>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className={`${TOUCH_TARGET_ROW} gap-1 px-2 -mr-2 text-xs font-medium text-blue-600 dark:text-blue-400 disabled:opacity-50`}
        >
          <RotateCw size={12} className={isFetching ? "animate-spin" : ""} />
          다시 시도
        </button>
      </div>
    );
  }
  if (!data) return null;

  if (data.length === 0) {
    return (
      <div className="card flex items-center gap-2">
        <CheckCircle2 size={16} className="shrink-0 text-green-500" />
        <p className="text-sm text-gray-600 dark:text-gray-400">
          지금 할 일이 없어요{" "}
          <span className="text-gray-400 dark:text-gray-500">— 모두 순항 중</span>
        </p>
      </div>
    );
  }

  const highCount = data.filter((it) => it.priority === "HIGH").length;
  return (
    <CollapsibleCard
      icon={ListChecks}
      iconWrapClassName="bg-blue-50 dark:bg-blue-950"
      iconColorClassName="text-blue-600 dark:text-blue-400"
      title="지금 할 일"
      titleBadge={
        <span
          className={`text-xs font-semibold rounded-full px-2 py-0.5 shrink-0 ${
            highCount > 0
              ? ACTION_PRIORITY_STYLE.HIGH.className
              : "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400"
          }`}
        >
          {highCount > 0 ? `우선 ${highCount}` : `${data.length}건`}
        </span>
      }
      isOpen={isOpen}
      onToggle={toggleOpen}
      collapsedHint={data[0].title}
    >
      <ul className={data.length > VISIBLE_LIMIT ? undefined : "-mb-3"}>
        {(showAll ? data : data.slice(0, VISIBLE_LIMIT)).map((item) => (
          <ActionRow key={item.id} item={item} marketSignal={marketSignal} />
        ))}
      </ul>
      {data.length > VISIBLE_LIMIT && (
        <button
          onClick={toggleShowAll}
          aria-expanded={showAll}
          className={`${TOUCH_TARGET_ROW} w-full gap-1 -mb-2 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200`}
        >
          {showAll ? "접기" : `${data.length - VISIBLE_LIMIT}개 더 보기`}
          <ChevronDown
            size={12}
            className={`transition-transform ${showAll ? "rotate-180" : ""}`}
          />
        </button>
      )}
    </CollapsibleCard>
  );
}
