import { Lightbulb } from "lucide-react";
import { Link } from "react-router-dom";
import type { OverseasPositionDetail } from "@/api/tax";
import { fmtKrw } from "@/utils/format";
import { posKey } from "@/hooks/useTaxSimulation";

interface Recommendation {
  pos: OverseasPositionDetail;
  label: string;
  taxSaved: number;
}

interface Props {
  recommendations: Recommendation[];
}

export function TaxRecommendationList({ recommendations }: Props) {
  return (
    <div className="rounded-xl border border-amber-200 dark:border-amber-800/50 bg-amber-50 dark:bg-amber-900/20 p-4 space-y-2">
      <div className="flex items-center gap-2">
        <Lightbulb size={13} className="text-amber-500 shrink-0" />
        <span className="text-xs font-semibold text-amber-700 dark:text-amber-400">
          절세 추천 — 세금 없이 실현 가능한 종목
        </span>
      </div>
      <ul className="space-y-1.5">
        {recommendations.map(({ pos, label, taxSaved }) => (
          <li
            key={`rec-${posKey(pos)}`}
            className="flex flex-wrap items-start justify-between gap-y-1 text-xs"
          >
            <span className="flex-1 min-w-0 text-gray-700 dark:text-gray-300">
              <span className="font-medium">{pos.ticker}</span>{" "}
              <span className="text-gray-500 dark:text-gray-400">{label}</span>
              {" → "}수익 {fmtKrw(pos.unrealized_pnl_krw)} 실현
              <Link
                to="/assets?tab=계좌관리&atab=증권계좌"
                className="ml-1.5 text-blue-600 dark:text-blue-400 hover:underline"
              >
                {pos.account_name}에서 매도 →
              </Link>
            </span>
            <span className="text-emerald-600 dark:text-emerald-400 font-medium ml-2 shrink-0">
              세금 절감 {fmtKrw(taxSaved)}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-amber-600 dark:text-amber-500 mt-1">
        * 수익 종목 테이블에서 매도 수량을 직접 입력하면 자세한 시뮬레이션을 확인할 수 있습니다.
      </p>
    </div>
  );
}
