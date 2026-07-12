import { CalendarClock } from "lucide-react";
import type { PortfolioOverview } from "@/types";
import { INVESTMENT_HORIZON_LABELS, InvestmentHorizon } from "@/api/assets";
import { fmtKrw } from "@/utils/format";

interface Props {
  overview: PortfolioOverview | undefined;
}

const HORIZON_ORDER: InvestmentHorizon[] = ["SHORT_TERM", "MID_TERM", "LONG_TERM"];

/** 계좌에 태그된 투자기간(단기/중기/장기)별 평가액 합계를 보여준다. 태그된 계좌가 하나도 없으면 표시하지 않는다. */
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
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 flex items-center gap-1.5">
          <CalendarClock size={16} className="text-teal-500" />
          투자기간별 자산현황
        </h2>
      </div>
      <div className="grid grid-cols-3 gap-2 sm:gap-4">
        {groups.map((g) => (
          <div key={g.horizon}>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">
              {INVESTMENT_HORIZON_LABELS[g.horizon]} ({g.count}개 계좌)
            </p>
            <p className="text-sm sm:text-base font-semibold text-gray-900 dark:text-gray-50 tabular-nums">
              {fmtKrw(g.amount)}
            </p>
            {totalTagged > 0 && (
              <p className="text-xs text-gray-400 dark:text-gray-500">
                {((g.amount / totalTagged) * 100).toFixed(0)}%
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
