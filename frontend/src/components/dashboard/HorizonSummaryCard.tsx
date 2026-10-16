import type { PortfolioOverview } from "@/types";
import { INVESTMENT_HORIZON_LABELS, InvestmentHorizon } from "@/api/assets";
import { clampPct, fmtKrw, fmtKrwShort } from "@/utils/format";

interface Props {
  overview: PortfolioOverview | undefined;
}

const HORIZON_ORDER: InvestmentHorizon[] = ["SHORT_TERM", "MID_TERM", "LONG_TERM"];
// 태그된 기간 수만큼만 열을 만들어 빈 칸이 남지 않게 한다
const GRID_COLS: Record<number, string> = {
  1: "sm:grid-cols-1",
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-3",
};
const HORIZON_BAR_COLOR: Record<InvestmentHorizon, string> = {
  SHORT_TERM: "bg-sky-300",
  MID_TERM: "bg-blue-400",
  LONG_TERM: "bg-indigo-500",
};

/** 계좌에 태그된 투자기간(단기/중기/장기)별 평가액 합계를 보여준다. 태그된 계좌가 하나도 없으면
 * 표시하지 않는다. 항상 상위 섹션(자산 › 투자현황) 내부에 임베드되는 형태로만 렌더된다. */
export default function HorizonSummaryCard({ overview }: Props) {
  const accounts = overview?.accounts ?? [];
  const tagged = accounts.filter((a) => a.investment_horizon);
  if (tagged.length === 0) return null;

  const totalTagged = tagged.reduce((sum, a) => sum + a.amount_krw, 0);
  const groups = HORIZON_ORDER.map((horizon) => {
    const group = tagged.filter((a) => a.investment_horizon === horizon);
    return {
      horizon,
      amount: group.reduce((sum, a) => sum + a.amount_krw, 0),
      count: group.length,
    };
  }).filter((g) => g.count > 0);

  const withPct = groups.map((g) => ({
    ...g,
    pct: totalTagged > 0 ? (g.amount / totalTagged) * 100 : 0,
  }));

  return (
    <div>
      <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase mb-1.5">
        투자기간별 자산현황
      </p>
      {/* 모바일: 스택 바 + 한 줄 범례(3열 미니 카드는 세로 공간을 많이 차지) */}
      <div className="sm:hidden">
        <div className="flex h-1.5 rounded-full overflow-hidden bg-gray-100 dark:bg-gray-700">
          {withPct.map((g) => (
            <div
              key={g.horizon}
              className={HORIZON_BAR_COLOR[g.horizon]}
              style={{ width: `${clampPct(g.pct)}%` }}
            />
          ))}
        </div>
        <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs">
          {withPct.map((g) => (
            <li
              key={g.horizon}
              className="flex items-center gap-1 min-w-0"
              aria-label={`${INVESTMENT_HORIZON_LABELS[g.horizon]} ${fmtKrw(g.amount)}, ${g.count}개 계좌, ${g.pct.toFixed(0)}%`}
            >
              <span
                aria-hidden="true"
                className={`w-2 h-2 rounded-sm shrink-0 ${HORIZON_BAR_COLOR[g.horizon]}`}
              />
              <span className="text-gray-500 dark:text-gray-400">
                {INVESTMENT_HORIZON_LABELS[g.horizon]}
              </span>
              <span className="font-semibold text-gray-800 dark:text-gray-100 tabular-nums">
                {fmtKrwShort(g.amount)}원
              </span>
              <span className="text-gray-400 dark:text-gray-500 tabular-nums">
                {g.pct.toFixed(0)}%
              </span>
            </li>
          ))}
        </ul>
      </div>
      <div className={`hidden sm:grid ${GRID_COLS[groups.length] ?? "sm:grid-cols-3"} sm:gap-4`}>
        {groups.map((g) => {
          const pct = totalTagged > 0 ? (g.amount / totalTagged) * 100 : 0;
          return (
            <div key={g.horizon} className="min-w-0">
              <p className="text-xs font-medium text-gray-600 dark:text-gray-300">
                {INVESTMENT_HORIZON_LABELS[g.horizon]}
              </p>
              <p className="text-base font-semibold text-gray-900 dark:text-gray-50 tabular-nums truncate">
                {fmtKrw(g.amount)}
              </p>
              <div className="mt-1 h-1 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
                <div
                  className="h-full rounded-full bg-blue-400"
                  style={{ width: `${clampPct(pct)}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500 tabular-nums">
                {g.count}개 계좌 · {pct.toFixed(0)}%
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
