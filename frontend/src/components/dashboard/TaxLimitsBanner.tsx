import { AlertTriangle, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useTaxLimitsSummary } from "@/hooks/useTaxLimitsSummary";
import type { PortfolioOverview } from "@/types";

interface Props {
  overview: PortfolioOverview | undefined;
}

/** ISA 만기·연금 공제한도·세금 추정 현황을 압축해 보여주고, 자산탭 세금 서브탭으로 딥링크한다.
 * `InvestmentSnapshotCard`("주식 투자 현황") 안의 4번째 하위 섹션으로, 형제 섹션인
 * "투자기간별 자산현황"/"배당 현황"과 동일한 시각 언어(아이콘 없는 텍스트 행)로 임베드된다 —
 * 상세는 여전히 /assets?tab=투자현황&portfolioTab=세금의 TaxLimitsSection/TaxOptimizationCard가 전담. */
export default function TaxLimitsBanner({ overview }: Props) {
  const { parts, warningText } = useTaxLimitsSummary(overview);

  if (parts.length === 0 && !warningText) return null;

  return (
    <div>
      <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase mb-1.5">
        세금 한도 요약
      </p>
      {warningText && (
        <div className="flex items-center gap-1.5 text-xs font-medium text-amber-600 dark:text-amber-400 mb-1.5">
          <AlertTriangle size={12} className="shrink-0" />
          <span className="truncate">{warningText}</span>
        </div>
      )}
      <div className="flex items-center gap-4 flex-wrap">
        <span className="text-xs font-semibold text-gray-800 dark:text-gray-200 tabular-nums">
          {parts.length > 0 ? parts.join(" · ") : "세금 현황 보기"}
        </span>
        <Link
          to="/assets?tab=투자현황&portfolioTab=세금"
          className="ml-auto flex items-center gap-1 text-xs text-blue-500 dark:text-blue-400 hover:underline"
        >
          자세히 보기 <ArrowRight size={11} />
        </Link>
      </div>
    </div>
  );
}
