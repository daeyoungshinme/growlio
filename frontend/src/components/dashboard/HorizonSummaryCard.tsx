import type { PortfolioOverview } from "@/types";
import { INVESTMENT_HORIZON_LABELS, InvestmentHorizon } from "@/api/assets";
import { clampPct, fmtKrw, fmtKrwShort } from "@/utils/format";

interface Props {
  overview: PortfolioOverview | undefined;
}

const HORIZON_ORDER: InvestmentHorizon[] = ["SHORT_TERM", "MID_TERM", "LONG_TERM"];
// 태그된 기간 수만큼만 열을 만들어 빈 칸이 남지 않게 한다
const GRID_COLS: Record<number, string> = { 1: "grid-cols-1", 2: "grid-cols-2", 3: "grid-cols-3" };

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

  return (
    <div>
      <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase mb-1.5">
        투자기간별 자산현황
      </p>
      <div className={`grid ${GRID_COLS[groups.length] ?? "grid-cols-3"} gap-2 sm:gap-4`}>
        {groups.map((g) => {
          const pct = totalTagged > 0 ? (g.amount / totalTagged) * 100 : 0;
          return (
            <div key={g.horizon} className="min-w-0">
              <p className="text-xs font-medium text-gray-600 dark:text-gray-300">
                {INVESTMENT_HORIZON_LABELS[g.horizon]}
              </p>
              {/* 360px 3열에서 "1.23억원"이 넘치지 않도록 모바일은 축약 금액 */}
              <p className="text-sm sm:text-base font-semibold text-gray-900 dark:text-gray-50 tabular-nums truncate">
                <span className="sm:hidden">{fmtKrwShort(g.amount)}원</span>
                <span className="hidden sm:inline">{fmtKrw(g.amount)}</span>
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
