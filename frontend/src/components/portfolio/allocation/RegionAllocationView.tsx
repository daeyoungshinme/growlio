import type { ReactNode } from "react";
import { fmtKrw, fmtKrwShort } from "@/utils/format";
import SegmentedControl from "./SegmentedControl";

export type RegionBasis = "exposure" | "listing";

const BASIS_OPTIONS = [
  { value: "exposure", label: "실제 투자지역" },
  { value: "listing", label: "상장시장" },
] as const;

const BASIS_HINT: Record<RegionBasis, string> = {
  exposure:
    "무엇에 투자하는지 기준이에요. 국내상장 미국 ETF(TIGER 미국S&P500 등)는 해외로 계산해요.",
  listing: "어느 거래소에 상장됐는지 기준이에요. 국내상장 해외 ETF도 국내로 계산해요.",
};

interface Segment {
  key: string;
  label: string;
  value: number;
  colorClassName: string;
}

interface Props {
  basis: RegionBasis;
  onBasisChange: (next: RegionBasis) => void;
  /** 선택한 기준의 금액. null이면 아직 계산 전(로딩·에러) — `fallback`을 대신 그린다. */
  amounts: { domestic: number; overseas: number; unknown?: number } | null;
  fallback?: ReactNode;
}

/** 국내/해외 비중 — 스택 바 + 범례. 실제 투자지역/상장시장 기준을 토글한다. */
export default function RegionAllocationView({ basis, onBasisChange, amounts, fallback }: Props) {
  const segments: Segment[] = amounts
    ? [
        {
          key: "domestic",
          label: "국내",
          value: amounts.domestic,
          colorClassName: "bg-indigo-500",
        },
        {
          key: "overseas",
          label: "해외",
          value: amounts.overseas,
          colorClassName: "bg-amber-400",
        },
        {
          key: "unknown",
          label: "판별 불가",
          value: amounts.unknown ?? 0,
          colorClassName: "bg-gray-300 dark:bg-gray-600",
        },
      ].filter((s) => s.value > 0)
    : [];
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  const pctOf = (v: number) => (total > 0 ? (v / total) * 100 : 0);

  return (
    <div>
      <SegmentedControl
        options={BASIS_OPTIONS}
        value={basis}
        onChange={onBasisChange}
        ariaLabel="국내/해외 기준"
      />
      <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{BASIS_HINT[basis]}</p>

      <div className="mt-3">
        {!amounts ? (
          fallback
        ) : total === 0 ? (
          <p className="py-4 text-center text-sm text-gray-400 dark:text-gray-500">데이터 없음</p>
        ) : (
          <>
            <div className="flex h-8 rounded-lg overflow-hidden" aria-hidden="true">
              {segments.map((s) => {
                const pct = pctOf(s.value);
                return (
                  <div
                    key={s.key}
                    className={`${s.colorClassName} flex items-center justify-center text-white text-xs font-medium transition-all`}
                    style={{ width: `${pct}%` }}
                  >
                    {pct >= 15 ? `${pct.toFixed(1)}%` : ""}
                  </div>
                );
              })}
            </div>
            <ul
              className={`mt-3 grid gap-2 ${segments.length > 2 ? "grid-cols-3" : "grid-cols-2"}`}
            >
              {segments.map((s) => (
                <li key={s.key} className="flex items-start gap-2 min-w-0">
                  <span className={`mt-1 w-3 h-3 rounded-sm shrink-0 ${s.colorClassName}`} />
                  <div className="min-w-0">
                    <div className="text-xs text-gray-500 dark:text-gray-400">{s.label}</div>
                    <div className="text-sm font-semibold text-gray-800 dark:text-gray-100 tabular-nums">
                      {pctOf(s.value).toFixed(1)}%
                    </div>
                    {/* 3칸 범례(판별 불가 포함)는 모바일에서 "1.23억원"이 잘려 축약 금액을 쓴다 */}
                    <div className="text-xs text-gray-500 dark:text-gray-400 tabular-nums truncate">
                      <span className="sm:hidden">{fmtKrwShort(s.value)}원</span>
                      <span className="hidden sm:inline">{fmtKrw(s.value)}</span>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
            {basis === "exposure" && (amounts.unknown ?? 0) > 0 && (
              <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                판별 불가: 종목명·추종 지수로 투자지역을 알 수 없는 ETF예요.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
