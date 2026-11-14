/** 투자현황 포트폴리오 목록의 카드 한 장 — 선택·목표 계좌 지정·이탈 상태·알림/자동화 상태·편집/삭제. */
import { memo } from "react";
import { TriangleAlert, Anchor, CircleCheck, Pen, GripVertical, Trash2 } from "lucide-react";
import { Portfolio } from "@/api/portfolios";
import type { PortfolioDriftSummary } from "@/api/rebalancing";
import { DRIFT_STATUS_LABEL, getDriftStatus } from "@/utils/portfolio";
import AutomationStatusBar from "@/components/rebalancing/AutomationStatusBar";
import {
  TOUCH_TARGET_COMPACT_MOBILE_ONLY,
  TOUCH_TARGET_MIN_MOBILE_ONLY,
} from "@/constants/uiSizes";
import { PIE_COLORS } from "@/utils/colors";

interface PortfolioCardProps {
  portfolio: Portfolio;
  selected: boolean;
  targetState: "full" | "partial" | "none";
  accountLabel: string;
  showAccountLabel: boolean;
  drift?: PortfolioDriftSummary;
  alertMode?: "NOTIFY" | "AUTO";
  hasAlert: boolean;
  isTargetPending: boolean;
  /** 없으면 순서 변경 핸들을 그리지 않는다(모바일 선택 카드 — 순서는 시트 목록에서) */
  dragHandleListeners?: React.HTMLAttributes<HTMLElement>;
  onToggleSelect: (id: string) => void;
  onOpenEditor: (portfolio: Portfolio) => void;
  onOpenAlertModal: (id: string) => void;
  onConfirmDelete: (id: string) => void;
  onToggleTarget: (e: React.MouseEvent, portfolio: Portfolio) => void;
}

const PortfolioCard = memo(function PortfolioCard({
  portfolio: p,
  selected,
  targetState: tState,
  accountLabel,
  showAccountLabel,
  drift,
  alertMode,
  hasAlert,
  isTargetPending,
  dragHandleListeners,
  onToggleSelect,
  onOpenEditor,
  onOpenAlertModal,
  onConfirmDelete,
  onToggleTarget,
}: PortfolioCardProps) {
  const driftStatus = drift
    ? drift.needs_rebalancing
      ? "critical"
      : getDriftStatus(drift.max_drift_pct, drift.threshold_pct)
    : null;
  const isNeeded = driftStatus === "critical";
  const isCaution = driftStatus === "caution";

  const sorted = p.items.length > 0 ? [...p.items].sort((a, b) => b.weight - a.weight) : [];
  const top = sorted.slice(0, 5);
  const rest = sorted.slice(5).reduce((s, i) => s + i.weight, 0);

  return (
    <div
      className={`rounded-xl border p-3.5 cursor-pointer transition-colors ${
        selected
          ? "border-blue-400 bg-blue-50 dark:bg-blue-950"
          : tState === "full"
            ? "border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-900 hover:bg-blue-50/50 dark:hover:bg-blue-950/40"
            : tState === "partial"
              ? "border-amber-200 dark:border-amber-700 bg-white dark:bg-gray-900 hover:bg-amber-50/50 dark:hover:bg-amber-950/40"
              : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800"
      }`}
      onClick={() => onToggleSelect(p.id)}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={`${p.name} 선택`}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onToggleSelect(p.id);
        }
      }}
    >
      {/* 행1: 드래그 핸들 + 이름/부제/미니바 + 수정/삭제 */}
      <div className="flex items-start gap-2">
        {dragHandleListeners && (
          <button
            {...dragHandleListeners}
            onClick={(e) => e.stopPropagation()}
            aria-label="포트폴리오 순서 변경"
            className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 cursor-grab active:cursor-grabbing shrink-0 touch-none`}
          >
            <GripVertical size={14} />
          </button>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-200 line-clamp-2 leading-snug">
            {p.name}
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate">
            {p.base_type === "STOCK_ONLY" ? "주식 기준" : "전체 자산"} · {p.items.length}개 항목
            {showAccountLabel && ` · ${accountLabel}`}
          </p>
          {top.length > 0 && (
            <div className="mt-1.5 flex h-2 rounded-full overflow-hidden gap-px">
              {top.map((item, ci) => (
                <div
                  key={item.ticker}
                  style={{
                    width: `${item.weight}%`,
                    backgroundColor: PIE_COLORS[ci],
                  }}
                />
              ))}
              {rest > 0 && <div style={{ width: `${rest}%`, backgroundColor: "#9CA3AF" }} />}
            </div>
          )}
          {/* 미니바 구성은 title로만 있어 터치에서 안 보였다 — 상위 3개를 글로 (plans/102 B2) */}
          {top.length > 0 && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 truncate">
              {top
                .slice(0, 3)
                .map((item) => `${item.name ?? item.ticker} ${item.weight.toFixed(0)}%`)
                .join(" · ")}
              {sorted.length > 3 && ` 외 ${sorted.length - 3}개`}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-0.5 shrink-0 mt-0.5">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onOpenEditor(p);
            }}
            aria-label="포트폴리오 수정"
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-1.5 text-gray-400 dark:text-gray-500 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors`}
          >
            <Pen size={14} />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onConfirmDelete(p.id);
            }}
            aria-label="포트폴리오 삭제"
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-1.5 text-gray-400 dark:text-gray-500 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors`}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>
      {/* 행2: 드리프트 배지(좌) + 목표/알림 버튼(우) */}
      <div className="mt-2 flex items-center gap-1.5">
        {drift &&
          (isNeeded ? (
            <span className="flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded-full font-medium bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-400">
              <TriangleAlert size={10} />
              {DRIFT_STATUS_LABEL.critical} {drift.max_drift_pct.toFixed(1)}%
            </span>
          ) : isCaution ? (
            <span className="flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded-full font-medium bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400">
              <TriangleAlert size={10} />
              {DRIFT_STATUS_LABEL.caution} {drift.max_drift_pct.toFixed(1)}%
            </span>
          ) : (
            <span className="flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded-full font-medium bg-green-100 dark:bg-green-950/60 text-green-700 dark:text-green-400">
              <CircleCheck size={10} />
              {DRIFT_STATUS_LABEL.stable}
            </span>
          ))}
        <div className="flex-1" />
        <button
          onClick={(e) => onToggleTarget(e, p)}
          disabled={isTargetPending}
          aria-label={tState !== "none" ? "기준 포트폴리오 해제" : "이 포트폴리오를 기준으로 지정"}
          className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-0.5 px-2 py-1 rounded-lg transition-colors text-xs font-medium ${
            tState === "full"
              ? "bg-blue-100 dark:bg-blue-950 text-blue-600 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-900"
              : tState === "partial"
                ? "bg-amber-100 dark:bg-amber-950 text-amber-600 dark:text-amber-400 hover:bg-amber-200 dark:hover:bg-amber-900"
                : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
          }`}
        >
          <Anchor size={11} />
          <span>{tState === "full" ? "기준" : tState === "partial" ? "일부" : "기준 지정"}</span>
        </button>
        <AutomationStatusBar
          existingAlert={hasAlert ? { mode: alertMode } : undefined}
          onOpenAlertModal={() => onOpenAlertModal(p.id)}
          compact
        />
      </div>
    </div>
  );
});

export default PortfolioCard;
