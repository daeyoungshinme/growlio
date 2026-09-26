import { TriangleAlert, ArrowRight, ListChecks } from "lucide-react";
import { fmtKrw } from "@/utils/format";
import { Link } from "react-router-dom";
import { useTaxLimitsSummary } from "@/hooks/useTaxLimitsSummary";
import type { PortfolioOverview } from "@/types";

interface Props {
  overview: PortfolioOverview | undefined;
}

/** ISA 만기·연금 공제한도·세금 추정 현황을 압축해 보여주고, 자산탭 세금 서브탭으로 딥링크한다.
 * 절세 액션 플랜에 액션이 있으면 한도 요약 줄 대신 최우선 액션 1줄을 보여준다(카드 높이 불변).
 * `InvestmentSnapshotCard`("주식 투자 현황") 안에 평가액·원금·손익 grid 아래 텍스트 행으로 임베드된다 —
 * 상세는 여전히 /assets?tab=투자현황&portfolioTab=세금의 `TaxTabContainer`(한도 현황/세금 추정 2탭)가 전담
 * — 기본 탭이 "한도 현황"이라 이 배너가 요약하는 내용과 자연스럽게 일치한다. */
export default function TaxLimitsBanner({ overview }: Props) {
  const { parts, warningText, topAction } = useTaxLimitsSummary(overview);

  if (parts.length === 0 && !warningText && !topAction) return null;

  return (
    <div>
      <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase mb-1.5">
        {topAction ? "절세 액션" : "세금 한도 요약"}
      </p>
      {warningText && (
        <div className="flex items-center gap-1.5 text-xs font-medium text-amber-600 dark:text-amber-400 mb-1.5">
          <TriangleAlert size={12} className="shrink-0" />
          <span className="truncate">{warningText}</span>
        </div>
      )}
      <div className="flex items-center gap-4 flex-wrap">
        {topAction ? (
          <span className="flex-1 min-w-0 flex items-center gap-1.5 text-xs font-semibold text-gray-800 dark:text-gray-200">
            <ListChecks size={12} className="shrink-0 text-blue-500" />
            <span className="truncate">{topAction.title}</span>
            {topAction.benefit_krw != null && topAction.benefit_krw > 0 && (
              <span className="shrink-0 text-emerald-600 dark:text-emerald-400 tabular-nums">
                절세 약 {fmtKrw(topAction.benefit_krw)}
              </span>
            )}
          </span>
        ) : (
          <span className="text-xs font-semibold text-gray-800 dark:text-gray-200 tabular-nums">
            {parts.length > 0 ? parts.join(" · ") : "세금 현황 보기"}
          </span>
        )}
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
