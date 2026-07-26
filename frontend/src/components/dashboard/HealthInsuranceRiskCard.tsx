import { useQuery } from "@tanstack/react-query";
import { fetchTaxSummary } from "@/api/tax";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { fmtKrw } from "@/utils/format";

function riskColor(pct: number): string {
  if (pct >= 100) return "text-red-600 dark:text-red-400";
  if (pct >= 80) return "text-amber-600 dark:text-amber-400";
  if (pct >= 50) return "text-blue-600 dark:text-blue-400";
  return "text-gray-500 dark:text-gray-400";
}

function riskBarColor(pct: number): string {
  if (pct >= 100) return "bg-red-500";
  if (pct >= 80) return "bg-amber-500";
  if (pct >= 50) return "bg-blue-500";
  return "bg-gray-400";
}

/** 배당소득 기준 건강보험 피부양자 자격상실 위험을 상시 노출한다(ISA/연금 계좌 유무와 무관 —
 * 배당소득은 계좌 태그가 아니라 전체 배당 수령액 기준). ISA/연금 계좌가 하나도 없어도 이 카드는
 * 항상 보여야 "세금탭에 아무것도 안 보인다"는 사각지대가 생기지 않는다.
 * `useTaxLimitsSummary`/`TaxOptimizationCard`와 동일 queryKey를 써서 React Query 캐시를 공유한다. */
export default function HealthInsuranceRiskCard() {
  const currentYear = new Date().getFullYear();
  const { data } = useQuery({
    queryKey: QUERY_KEYS.taxSummary(currentYear, undefined),
    queryFn: () => fetchTaxSummary(currentYear, undefined),
    staleTime: STALE_TIME.LONG,
  });

  if (!data) return null;

  const est = data.health_insurance_estimate;
  const pct =
    est.threshold_krw > 0
      ? (est.financial_income_for_health_insurance_krw / est.threshold_krw) * 100
      : 0;

  return (
    <div>
      <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase mb-1.5">
        건강보험 피부양자 기준 ({currentYear}년)
      </p>
      <div className="bg-white dark:bg-gray-900 p-2">
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">배당소득 / 자격상실 기준</p>
        <span className={`text-sm font-bold ${riskColor(pct)}`}>
          {Math.min(pct, 999).toFixed(1)}%
        </span>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {fmtKrw(est.financial_income_for_health_insurance_krw)} / {fmtKrw(est.threshold_krw)}
        </p>
        <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1 mt-1">
          <div
            className={`h-full rounded-full ${riskBarColor(pct)}`}
            style={{ width: `${Math.min(Math.max(pct, 0), 100)}%` }}
          />
        </div>
        {est.dependent_risk_warning && (
          <p className="text-xs text-red-600 dark:text-red-400 mt-1.5 font-medium">
            자격상실 위험 — 지역가입자 전환 시 예상 월 보험료 약{" "}
            {fmtKrw(est.estimated_monthly_premium_krw ?? 0)}
          </p>
        )}
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">{est.note}</p>
    </div>
  );
}
