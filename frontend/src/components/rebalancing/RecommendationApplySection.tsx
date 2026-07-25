import type { ReactNode } from "react";
import { Anchor, FolderPlus, Loader2 } from "lucide-react";
import type { Portfolio } from "@/api/portfolios";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";

interface Props {
  /** 적용 대상 후보 포트폴리오 — 0개면 안내 문구, 1개면 이름을 바로 노출, 2개 이상이면 select로 선택.
   * 기간별 탭처럼 대상이 태그 매칭으로 이미 하나로 확정되는 경우 그 하나만(또는 0개를) 담아 전달한다. */
  targetPortfolios: Portfolio[];
  selectedTargetId: string;
  onSelectTarget: (id: string) => void;
  onApplyClick: () => void;
  applyPending: boolean;
  /** targetPortfolios가 비어있을 때 보여줄 안내 문구 — 탭마다 문구가 다르다. */
  noTargetMessage: string;
  /** 적용 버튼 위에 추가로 보여줄 문구(기간별 탭의 현금성 자산 자동 연결 안내 등). */
  extraCopyBeforeButtons?: ReactNode;
  onCreatePortfolio?: () => void;
}

/** 전체/연령대/기간별 3개 탭이 공유하는 "대상 포트폴리오 선택 + 적용 버튼 + 새 포트폴리오 만들기
 * 버튼" 패턴 — 3탭 모두 거의 동일한 마크업을 반복하던 것을 하나로 통합한다. */
export default function RecommendationApplySection({
  targetPortfolios,
  selectedTargetId,
  onSelectTarget,
  onApplyClick,
  applyPending,
  noTargetMessage,
  extraCopyBeforeButtons,
  onCreatePortfolio,
}: Props) {
  return (
    <div className="pt-2 border-t border-teal-200 dark:border-teal-800/50 space-y-2">
      {extraCopyBeforeButtons}
      {targetPortfolios.length === 0 ? (
        <p className="text-xs text-gray-500 dark:text-gray-400">{noTargetMessage}</p>
      ) : (
        <div className="flex items-center gap-2 flex-wrap">
          {targetPortfolios.length > 1 && (
            <select
              value={selectedTargetId}
              onChange={(e) => onSelectTarget(e.target.value)}
              className="text-xs border border-teal-200 dark:border-teal-800/50 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg px-2 py-2 sm:py-1.5 focus:outline-none focus:ring-2 focus:ring-teal-500"
            >
              <option value="">포트폴리오 선택</option>
              {targetPortfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            disabled={(targetPortfolios.length > 1 && !selectedTargetId) || applyPending}
            onClick={onApplyClick}
            className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-1 text-xs font-medium text-white bg-teal-600 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed px-3 py-1.5 rounded-lg transition-colors`}
          >
            {applyPending ? <Loader2 size={12} className="animate-spin" /> : <Anchor size={12} />}
            {targetPortfolios.length === 1
              ? `${targetPortfolios[0].name}에 적용`
              : "기준 포트폴리오에 적용"}
          </button>
        </div>
      )}
      {onCreatePortfolio && (
        <button
          type="button"
          onClick={onCreatePortfolio}
          className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-1 text-xs font-medium text-teal-700 dark:text-teal-400 border border-teal-300 dark:border-teal-700 hover:bg-teal-100 dark:hover:bg-teal-900/40 px-3 py-1.5 rounded-lg transition-colors`}
        >
          <FolderPlus size={12} />이 비중으로 새 포트폴리오 만들기
        </button>
      )}
    </div>
  );
}
