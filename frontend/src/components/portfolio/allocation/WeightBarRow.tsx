import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { DOMESTIC_MARKETS } from "@/constants";
import { TOUCH_TARGET_ROW } from "@/constants/uiSizes";
import { clampPct } from "@/utils/format";
import { weightBarColor } from "@/utils/dividendUtils";

/** 국내/해외 배지 — 상장시장 또는 실제 투자지역 표시에 공용. */
export function RegionBadge({ domestic, children }: { domestic: boolean; children?: ReactNode }) {
  return (
    <span
      className={`shrink-0 text-xs px-1.5 py-0.5 rounded ${
        domestic
          ? "bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400"
          : "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-400"
      }`}
    >
      {children ?? (domestic ? "국내" : "해외")}
    </span>
  );
}

/** 상장시장 배지 — "국내"/"해외"만 쓰면 실제 투자지역과 헷갈리므로 "상장"을 붙인다. */
export function ListingBadge({ market }: { market: string }) {
  const domestic = DOMESTIC_MARKETS.includes(market.toUpperCase());
  return <RegionBadge domestic={domestic}>{domestic ? "국내상장" : "해외상장"}</RegionBadge>;
}

interface Props {
  label: ReactNode;
  pct: number;
  /** 라벨 앞 순위 번호 등 */
  leading?: ReactNode;
  /** 라벨 뒤 배지 */
  badges?: ReactNode;
  subLeft?: ReactNode;
  subRight?: ReactNode;
  /** 막대 색 — 기본은 비중 구간색(25% 이상 강조) */
  barClassName?: string;
  /** 있으면 행을 눌러 펼칠 수 있다 */
  children?: ReactNode;
}

/** 비중 분석 카드의 공용 행: 라벨 · 비중% · 막대 · 보조문구/금액 (+선택적 펼침). */
export default function WeightBarRow({
  label,
  pct,
  leading,
  badges,
  subLeft,
  subRight,
  barClassName,
  children,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const expandable = children != null && children !== false;

  const body = (
    <div className="min-w-0 flex-1">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 min-w-0">
          {leading}
          <span className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
            {label}
          </span>
          {badges}
        </span>
        <span className="shrink-0 text-sm font-semibold text-gray-800 dark:text-gray-200 tabular-nums">
          {pct.toFixed(1)}%
        </span>
      </div>
      <div className="mt-1 h-1.5 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
        <div
          className={`h-full rounded-full ${barClassName ?? weightBarColor(pct)}`}
          style={{ width: `${clampPct(pct)}%` }}
        />
      </div>
      {(subLeft != null || subRight != null) && (
        <div className="mt-1 flex items-center justify-between gap-2 text-xs text-gray-500 dark:text-gray-400">
          <span className="truncate">{subLeft}</span>
          <span className="shrink-0 tabular-nums">{subRight}</span>
        </div>
      )}
    </div>
  );

  return (
    <li className="py-2">
      {expandable ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className={`w-full text-left gap-2 ${TOUCH_TARGET_ROW}`}
        >
          {body}
          <ChevronDown
            size={14}
            className={`text-gray-400 shrink-0 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
          />
        </button>
      ) : (
        <div className="flex">{body}</div>
      )}
      {expandable && expanded && children}
    </li>
  );
}
