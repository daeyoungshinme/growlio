import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronRight, ListChecks } from "lucide-react";
import { fetchActionItems, type ActionItem } from "@/api/dashboard";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { useCollapsible } from "@/hooks/useCollapsible";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import SkeletonCard from "@/components/common/SkeletonCard";
import { ACTION_PRIORITY_STYLE, deadlineLabel } from "@/utils/actionPriority";

function ActionRow({ item }: { item: ActionItem }) {
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
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">{item.title}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-relaxed">
            {item.detail}
          </p>
          <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mt-1">
            {item.cta_label}
            {item.deadline && (
              <span className="ml-2 font-normal text-gray-400 dark:text-gray-500">
                {deadlineLabel(item.deadline)}
              </span>
            )}
          </p>
        </div>
        <ChevronRight size={16} className="mt-0.5 shrink-0 text-gray-300 dark:text-gray-600" />
      </Link>
    </li>
  );
}

/** 홈 "지금 할 일" — 리밸런싱 필요·자동매수 예수금 부족·세금 경고·절세 1순위·챌린지 미입금을
 * 우선순위 리스트 1장으로 모은다(docs/plans/50 M5). 집계·정렬은 백엔드 `/dashboard/action-items`. */
export default function ActionItemsCard() {
  const [isOpen, toggleOpen] = useCollapsible(true, "growlio:dashboard:actionItemsOpen");
  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.actionItems,
    queryFn: fetchActionItems,
    staleTime: STALE_TIME.MEDIUM,
  });

  if (isLoading) return <SkeletonCard rows={2} />;
  // 집계 실패는 홈 전체를 막지 않는다 — 각 신호의 상세 화면은 그대로 동작
  if (isError || !data) return null;

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
      <ul className="-mb-3">
        {data.map((item) => (
          <ActionRow key={item.id} item={item} />
        ))}
      </ul>
    </CollapsibleCard>
  );
}
