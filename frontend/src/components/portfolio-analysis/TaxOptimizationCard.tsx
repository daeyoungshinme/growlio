import { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronUp, Receipt } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchOverseasPositionsTax, fetchTaxSummary } from "@/api/tax";
import TaxPlannerSection from "@/components/tax/TaxPlannerSection";
import { GeumtSimulationSection } from "@/components/tax/GeumtSimulationSection";
import ErrorBoundary from "@/components/ErrorBoundary";
import { fmtKrw } from "@/utils/format";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { SELECT_SM } from "@/constants/inputStyles";

export default function TaxOptimizationCard() {
  const currentYear = new Date().getFullYear();
  const [taxYear, setTaxYear] = useState(currentYear);
  const [plannerOpen, setPlannerOpen] = useState(false);
  const [geumtOpen, setGeumtOpen] = useState(false);

  const { data: taxData, isLoading: taxLoading } = useQuery({
    queryKey: QUERY_KEYS.taxSummary(taxYear),
    queryFn: () => fetchTaxSummary(taxYear),
    staleTime: STALE_TIME.LONG,
  });

  const { data: positionsData, isLoading: posLoading } = useQuery({
    queryKey: QUERY_KEYS.overseasPositionsTax,
    queryFn: fetchOverseasPositionsTax,
    staleTime: STALE_TIME.MEDIUM,
    enabled: plannerOpen,
  });

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Receipt size={15} className="text-blue-500" />
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">세금 추정</h3>
          <span className="text-xs text-gray-400 dark:text-gray-500">배당세·해외 양도세</span>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 dark:text-gray-400 font-medium">기준 연도</label>
          <select
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

      {taxData && !taxLoading && (
        <div className="space-y-3">
          {(taxData.domestic_large_holder_warning || taxData.comprehensive_tax_warning) && (
            <div className="space-y-2">
              {taxData.domestic_large_holder_warning && (
                <div className="flex items-start gap-2 p-3 bg-orange-50 dark:bg-orange-900/20 rounded-lg">
                  <AlertTriangle size={14} className="text-orange-500 mt-0.5 shrink-0" />
                  <p className="text-xs text-orange-700 dark:text-orange-400">
                    국내 주식 보유액이 10억원 이상입니다. 대주주 요건 해당 시 양도소득세(22%)가
                    부과될 수 있습니다.
                  </p>
                </div>
              )}
              {taxData.comprehensive_tax_warning && (
                <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                  <AlertTriangle size={14} className="text-red-500 mt-0.5 shrink-0" />
                  <p className="text-xs text-red-700 dark:text-red-400">
                    금융소득(배당+해외차익)이 2,000만원 이상입니다. 금융소득 종합과세 대상이 될 수
                    있습니다.
                  </p>
                </div>
              )}
            </div>
          )}

          <div className="flex divide-x divide-gray-200 dark:divide-gray-700 bg-gray-50 dark:bg-gray-800 rounded-xl overflow-hidden">
            <div className="flex-1 min-w-0 px-3 py-2.5">
              <p className="text-xs text-gray-500 dark:text-gray-400 font-medium truncate">
                배당소득세
              </p>
              <p className="text-base font-bold text-gray-900 dark:text-gray-50 mt-0.5 truncate">
                {fmtKrw(taxData.dividend_tax_krw)}
              </p>
              <p className="hidden sm:block text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate">
                배당수령 {fmtKrw(taxData.dividend_income_krw)} ×{" "}
                {taxData.rates.dividend_tax_rate_pct}%
              </p>
            </div>
            <div className="flex-1 min-w-0 px-3 py-2.5">
              <p className="text-xs text-gray-500 dark:text-gray-400 font-medium truncate">
                해외 양도세
              </p>
              <p className="text-base font-bold text-gray-900 dark:text-gray-50 mt-0.5 truncate">
                {fmtKrw(taxData.overseas_tax_estimated_krw)}
              </p>
              <p className="hidden sm:block text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate">
                미실현 {fmtKrw(taxData.overseas_unrealized_gain_krw)} (
                {taxData.rates.overseas_tax_rate_pct}%)
              </p>
            </div>
            <div className="flex-1 min-w-0 px-3 py-2.5 bg-blue-50 dark:bg-blue-900/20">
              <p className="text-xs text-blue-600 dark:text-blue-400 font-medium truncate">
                예상 납부
              </p>
              <p className="text-base font-bold text-blue-700 dark:text-blue-300 mt-0.5 truncate">
                {fmtKrw(taxData.total_estimated_tax_krw)}
              </p>
              <p className="hidden sm:block text-xs text-blue-500 dark:text-blue-500 mt-0.5">
                {taxYear}년 기준
              </p>
            </div>
          </div>

          <p className="text-xs text-gray-400 dark:text-gray-500">{taxData.note}</p>

          <button
            onClick={() => setPlannerOpen((v) => !v)}
            className="w-full flex items-center justify-between py-2 text-xs font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 border-t border-gray-100 dark:border-gray-700 pt-3 transition-colors"
          >
            <span>절세 플래너 — 해외 종목 매도 시뮬레이션</span>
            {plannerOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {plannerOpen &&
            (posLoading ? (
              <p className="text-sm text-gray-400 dark:text-gray-500">불러오는 중...</p>
            ) : positionsData ? (
              <ErrorBoundary variant="section">
                <TaxPlannerSection positions={positionsData} />
              </ErrorBoundary>
            ) : null)}

          <button
            onClick={() => setGeumtOpen((v) => !v)}
            className="w-full flex items-center justify-between py-2 text-xs font-medium text-violet-600 dark:text-violet-400 hover:text-violet-700 dark:hover:text-violet-300 border-t border-gray-100 dark:border-gray-700 pt-3 transition-colors"
          >
            <span>금투세 시뮬레이션 — 유예 중 세제 미리 보기</span>
            {geumtOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {geumtOpen && taxData.financial_investment_tax_simulation && (
            <ErrorBoundary variant="section">
              <GeumtSimulationSection
                sim={taxData.financial_investment_tax_simulation}
                currentOverseasTax={taxData.overseas_tax_estimated_krw}
              />
            </ErrorBoundary>
          )}
        </div>
      )}
    </div>
  );
}
