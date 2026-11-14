import { useId, useState } from "react";
import { TriangleAlert, ChevronDown, ChevronUp, Receipt } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchOverseasPositionsTax, fetchOverseasRealized, type TaxSummary } from "@/api/tax";
import TaxPlannerSection from "@/components/tax/TaxPlannerSection";
import ErrorBoundary from "@/components/ErrorBoundary";
import { fmtKrw } from "@/utils/format";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { taxSummaryQuery } from "@/api/queryOptions";
import { STALE_TIME } from "@/constants/queryConfig";
import { SELECT_SM } from "@/constants/inputStyles";
import { TOUCH_HEIGHT_MIN } from "@/constants/uiSizes";
import EmptyState from "@/components/common/EmptyState";

interface TaxOptimizationCardProps {
  /** 특정 계좌만 필터링해 조회 (미지정 시 전체 계좌 통합) */
  accountId?: string | null;
}

/** 종합과세 기준까지 이 금액 이하로 남으면 "곧 근접" 경고를 보여준다 */
const COMPREHENSIVE_TAX_NEAR_THRESHOLD_KRW = 5_000_000;
/** 건강보험 피부양자 자격상실 기준까지 이 금액 이하로 남으면 "곧 근접" 경고를 보여준다 */
const HEALTH_INSURANCE_NEAR_THRESHOLD_KRW = 5_000_000;

export default function TaxOptimizationCard({ accountId }: TaxOptimizationCardProps = {}) {
  const currentYear = new Date().getFullYear();
  const taxYearId = useId();
  const [taxYear, setTaxYear] = useState(currentYear);
  // 플래너는 기본 접힘 — 손실수확 후보가 있으면 토글 옆 "손실수확 가능" 배지로 알린다. 예전처럼 자동으로
  // 펼치면 절세 탭이 표·입력폼까지 한 번에 길어졌다 (docs/plans/67 Phase 3)
  const [plannerOpenOverride, setPlannerOpenOverride] = useState<boolean | null>(null);

  const {
    data: taxData,
    isLoading: taxLoading,
    isError: taxFailed,
    refetch: refetchTax,
  } = useQuery(taxSummaryQuery(taxYear, accountId));

  const hasLossHarvestCandidates = (taxData?.overseas_unrealized_gain_krw ?? 0) < 0;
  const plannerOpen = plannerOpenOverride ?? false;

  const {
    data: positionsData,
    isLoading: posLoading,
    isError: positionsFailed,
    refetch: refetchPositions,
  } = useQuery({
    queryKey: QUERY_KEYS.overseasPositionsTax(accountId),
    queryFn: () => fetchOverseasPositionsTax(accountId),
    staleTime: STALE_TIME.MEDIUM,
    enabled: plannerOpen,
  });

  // 플래너는 올해 기준 — 증권사 체결 기준 올해 실현손익(KIS 실전 계좌 자동 집계)을 기본값으로 쓴다
  const {
    data: realizedData,
    isLoading: realizedLoading,
    isError: realizedFailed,
  } = useQuery({
    queryKey: QUERY_KEYS.overseasRealized(currentYear, accountId),
    queryFn: () => fetchOverseasRealized(currentYear, accountId),
    staleTime: STALE_TIME.MEDIUM,
    enabled: plannerOpen,
  });
  const interestIncome = taxData?.interest_income_krw ?? 0;

  return (
    <div className="card space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-y-2">
        <div className="flex items-center gap-2 shrink-0">
          <Receipt size={15} className="text-blue-500 shrink-0" />
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 whitespace-nowrap">
            세금 추정
          </h3>
          <span className="text-xs text-gray-500 dark:text-gray-400">배당세·해외 양도세</span>
        </div>
        <div className="flex items-center gap-2">
          <label
            htmlFor={taxYearId}
            className="text-xs text-gray-500 dark:text-gray-400 font-medium"
          >
            기준 연도
          </label>
          <select
            id={taxYearId}
            value={taxYear}
            onChange={(e) => setTaxYear(Number(e.target.value))}
            className={SELECT_SM}
          >
            {[currentYear, currentYear - 1, currentYear - 2].map((y) => (
              <option key={y} value={y}>
                {y}년
              </option>
            ))}
          </select>
        </div>
      </div>

      {taxLoading && <p className="text-sm text-gray-400 dark:text-gray-500">계산 중...</p>}

      {taxFailed && !taxData && (
        <EmptyState
          title="세금 추정을 불러오지 못했습니다."
          action={{ label: "다시 시도", onClick: () => void refetchTax() }}
          compact
        />
      )}

      {taxData && !taxLoading && (
        <div className="space-y-3">
          {taxData.domestic_large_holder_warning && (
            <div className="flex items-start gap-2 p-3 bg-orange-50 dark:bg-orange-900/20 rounded-lg">
              <TriangleAlert size={14} className="text-orange-500 mt-0.5 shrink-0" />
              <p className="text-xs text-orange-700 dark:text-orange-400">
                {taxData.domestic_large_holder_name ?? "보유 종목"} 보유액이 대주주 기준(
                {fmtKrw(taxData.domestic_large_holder_threshold_krw)}) 이상이에요. 판정은
                종목별·직전 연도 말 기준이고 지분율 요건도 함께 봐요. 대주주에 해당하면 양도소득세가
                부과될 수 있으니 세무 전문가와 확인해 보세요.
              </p>
            </div>
          )}

          <FinancialIncomeThresholdNotice taxData={taxData} />

          <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-gray-200 dark:divide-gray-700 bg-gray-50 dark:bg-gray-800 rounded-xl overflow-hidden">
            <div className="min-w-0 px-3 py-2.5">
              <p className="text-xs text-gray-500 dark:text-gray-400 font-medium truncate">
                {interestIncome > 0 ? "배당·이자소득세" : "배당소득세"}
              </p>
              <p className="text-base font-bold text-gray-900 dark:text-gray-50 mt-0.5 truncate">
                {fmtKrw(taxData.dividend_tax_krw + (taxData.interest_tax_krw ?? 0))}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 break-keep">
                {interestIncome > 0
                  ? `배당 ${fmtKrw(taxData.dividend_income_krw)} + 이자 ${fmtKrw(interestIncome)}`
                  : `과세계좌 배당 ${fmtKrw(taxData.dividend_income_krw)}`}{" "}
                × {taxData.rates.dividend_tax_rate_pct}%
              </p>
            </div>
            <div className="min-w-0 px-3 py-2.5">
              <p className="text-xs text-gray-500 dark:text-gray-400 font-medium truncate">
                해외 양도세
              </p>
              <p className="text-base font-bold text-gray-900 dark:text-gray-50 mt-0.5 truncate">
                {fmtKrw(taxData.overseas_tax_estimated_krw)}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 break-keep">
                {taxData.overseas_realized_gain_krw != null &&
                  `실현 ${fmtKrw(taxData.overseas_realized_gain_krw)} + `}
                미실현 {fmtKrw(taxData.overseas_unrealized_gain_krw)} (
                {taxData.rates.overseas_tax_rate_pct}%)
              </p>
            </div>
            <div className="min-w-0 px-3 py-2.5 bg-blue-50 dark:bg-blue-900/20">
              <p className="text-xs text-blue-600 dark:text-blue-400 font-medium truncate">
                예상 납부
              </p>
              <p className="text-base font-bold text-blue-700 dark:text-blue-300 mt-0.5 truncate">
                {fmtKrw(taxData.total_estimated_tax_krw)}
              </p>
              <p className="text-xs text-blue-500 dark:text-blue-500 mt-0.5">{taxYear}년 기준</p>
            </div>
          </div>

          <p className="text-xs text-gray-500 dark:text-gray-400">{taxData.note}</p>

          <button
            onClick={() => setPlannerOpenOverride(!plannerOpen)}
            aria-expanded={plannerOpen}
            className={`w-full flex items-center justify-between ${TOUCH_HEIGHT_MIN} text-xs font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 border-t border-gray-100 dark:border-gray-700 pt-3 transition-colors`}
          >
            <span className="flex items-center gap-1.5">
              <span className="text-left break-keep">절세 플래너 — 해외 종목 매도 시뮬레이션</span>
              {hasLossHarvestCandidates && (
                <span className="shrink-0 px-1.5 py-0.5 text-xs font-semibold bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full">
                  손실수확 가능
                </span>
              )}
            </span>
            {plannerOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {plannerOpen &&
            (posLoading || realizedLoading ? (
              <p className="text-sm text-gray-400 dark:text-gray-500">불러오는 중...</p>
            ) : positionsData ? (
              <ErrorBoundary variant="section">
                <TaxPlannerSection
                  positions={positionsData}
                  realized={realizedData}
                  realizedFailed={realizedFailed}
                  taxRule={{
                    deduction: taxData.overseas_gain_deduction_krw,
                    rate: taxData.rates.overseas_tax_rate_pct / 100,
                  }}
                />
              </ErrorBoundary>
            ) : positionsFailed ? (
              <EmptyState
                title="해외 종목을 불러오지 못했습니다."
                action={{ label: "다시 시도", onClick: () => void refetchPositions() }}
                compact
              />
            ) : null)}
        </div>
      )}
    </div>
  );
}

/** 금융소득 2,000만원 경고 — 종합과세와 건보 피부양자 자격상실은 같은 기준선이라 박스 하나로 묶는다.
 * 예전엔 최대 3개의 색 박스가 쌓였다 (docs/plans/67 P1-16). */
function FinancialIncomeThresholdNotice({ taxData }: { taxData: TaxSummary }) {
  const hi = taxData.health_insurance_estimate;
  const comprehensiveNear =
    !taxData.comprehensive_tax_warning &&
    taxData.comprehensive_tax_remaining_krw > 0 &&
    taxData.comprehensive_tax_remaining_krw <= COMPREHENSIVE_TAX_NEAR_THRESHOLD_KRW;
  const healthNear =
    !hi.dependent_risk_warning &&
    hi.income_remaining_until_risk_krw <= HEALTH_INSURANCE_NEAR_THRESHOLD_KRW;
  const exceeded = taxData.comprehensive_tax_warning || hi.dependent_risk_warning;
  if (!exceeded && !comprehensiveNear && !healthNear) return null;

  const lines: string[] = [];
  if (taxData.comprehensive_tax_warning) lines.push("금융소득 종합과세 대상이 될 수 있어요.");
  else if (comprehensiveNear)
    lines.push(`종합과세 기준까지 ${fmtKrw(taxData.comprehensive_tax_remaining_krw)} 남았어요.`);
  if (hi.dependent_risk_warning)
    lines.push(
      `건강보험 피부양자 자격을 잃을 수 있어요 — 지역가입자 전환 시 월 약 ${fmtKrw(hi.estimated_monthly_premium_krw ?? 0)}.`,
    );
  else if (healthNear)
    lines.push(
      `건강보험 피부양자 기준까지 ${fmtKrw(hi.income_remaining_until_risk_krw)} 남았어요.`,
    );

  const tone = exceeded
    ? {
        box: "bg-red-50 dark:bg-red-900/20",
        icon: "text-red-500",
        text: "text-red-700 dark:text-red-400",
      }
    : {
        box: "bg-amber-50 dark:bg-amber-900/20",
        icon: "text-amber-500",
        text: "text-amber-700 dark:text-amber-400",
      };

  return (
    <div className="space-y-1">
      <div className={`flex items-start gap-2 p-3 rounded-lg ${tone.box}`}>
        <TriangleAlert size={14} className={`${tone.icon} mt-0.5 shrink-0`} />
        <div className={`text-xs ${tone.text} space-y-0.5`}>
          <p className="font-semibold">
            금융소득(이자·배당) 2,000만원 {exceeded ? "이상" : "근접"}
          </p>
          {lines.map((l) => (
            <p key={l}>{l}</p>
          ))}
        </div>
      </div>
      {(hi.dependent_risk_warning || healthNear) && hi.note && (
        <p className="text-xs text-gray-500 dark:text-gray-400 pl-1">{hi.note}</p>
      )}
    </div>
  );
}
