import { Info, TrendingUp, TrendingDown, Lightbulb } from "lucide-react";
import type { OverseasPositionDetail } from "@/api/tax";
import { fmtKrw } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { useTaxSimulation, TAX_DEDUCTION } from "@/hooks/useTaxSimulation";
import { TaxPositionTable } from "./TaxPositionTable";
import { TaxSimulationCard } from "./TaxSimulationCard";
import { TaxRecommendationList } from "./TaxRecommendationList";

interface Props {
  positions: OverseasPositionDetail[];
}

export default function TaxPlannerSection({ positions }: Props) {
  const {
    alreadyRealizedInput,
    setAlreadyRealizedInput,
    sellQtyMap,
    alreadyRealized,
    profitPositions,
    lossPositions,
    totalLoss,
    remainingDeduction,
    maxTaxFreeProfit,
    currentTax,
    deductionUsedPct,
    totalSimPnl,
    hasAnyQtyInput,
    simTotalRealized,
    simTax,
    simTaxDiff,
    recommendations,
    handleQtyChange,
  } = useTaxSimulation(positions);

  if (positions.length === 0) {
    return (
      <div className="mt-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 p-4 text-center text-sm text-gray-400 dark:text-gray-500">
        해외 종목 보유 현황이 없습니다.
      </div>
    );
  }

  return (
    <div className="mt-4 space-y-4">
      <div className="flex items-center gap-2">
        <Lightbulb size={15} className="text-amber-500 shrink-0" />
        <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
          해외 양도세 절세 플래너
        </span>
        <span className="text-xs text-gray-400 dark:text-gray-500">250만원 공제 최대 활용</span>
      </div>

      {/* 올해 이미 실현한 손익 입력 + 공제 현황 */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-3">
        <div className="flex items-start gap-2 p-2.5 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
          <Info size={13} className="text-blue-500 mt-0.5 shrink-0" />
          <p className="text-xs text-blue-700 dark:text-blue-300 leading-relaxed">
            <span className="font-medium">배당금은 250만원 공제 대상이 아닙니다.</span> 배당금은
            배당소득세(15.4%)로 별도 원천징수됩니다. 이 플래너는 해외 주식
            <span className="font-medium"> 매매 차익(양도소득)</span>만 계산합니다. 단, 배당금 +
            양도차익 합계가 연 2,000만원 초과 시 금융소득 종합과세 대상이 될 수 있습니다.
          </p>
        </div>

        <div className="flex items-start gap-2">
          <Info size={13} className="text-gray-400 mt-0.5 shrink-0" />
          <p className="text-xs text-gray-500 dark:text-gray-400">
            올해 이미 해외 주식을 매도해 실현한 손익이 있다면 입력하세요 (양도차익만, 배당금 제외).
            없으면 0.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 shrink-0">
            올해 실현 손익 (원)
          </label>
          <input
            type="text"
            inputMode="numeric"
            value={alreadyRealizedInput}
            onChange={(e) => setAlreadyRealizedInput(e.target.value)}
            placeholder="0"
            className="w-36 min-w-0 border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {alreadyRealized !== 0 && (
            <span className={`text-xs font-medium ${pnlColor(alreadyRealized)}`}>
              {fmtKrw(alreadyRealized)}
            </span>
          )}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500 dark:text-gray-400">공제 사용 현황</span>
            <span className="font-medium text-gray-700 dark:text-gray-300">
              {fmtKrw(Math.max(0, alreadyRealized))} / {fmtKrw(TAX_DEDUCTION)}
            </span>
          </div>
          <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                deductionUsedPct >= 100
                  ? "bg-red-400"
                  : deductionUsedPct >= 70
                    ? "bg-amber-400"
                    : "bg-emerald-400"
              }`}
              style={{ width: `${deductionUsedPct}%` }}
            />
          </div>
          <div className="flex flex-wrap items-start justify-between gap-y-1">
            <div className="flex-1 min-w-0">
              {alreadyRealized < TAX_DEDUCTION ? (
                <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                  공제 잔여 {fmtKrw(remainingDeduction)} — 세금 없이 이만큼 더 수익 실현 가능
                </span>
              ) : (
                <span className="text-xs text-red-500 dark:text-red-400 font-medium">
                  공제 초과 — 초과분에 22% 과세 (현재 예상세금 {fmtKrw(currentTax)})
                </span>
              )}
            </div>
            {totalLoss < 0 && (
              <span className="text-xs text-blue-500 dark:text-blue-400 shrink-0">
                손실 통산 시 {fmtKrw(maxTaxFreeProfit)}까지 무세 실현
              </span>
            )}
          </div>
        </div>
      </div>

      {profitPositions.length > 0 && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 dark:border-gray-800">
            <TrendingUp size={14} className="text-red-400" />
            <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
              수익 종목
            </span>
            <span className="hidden sm:inline ml-1 text-xs text-gray-400 dark:text-gray-500">
              — 매도 수량을 입력해 세금을 계산하세요
            </span>
            <span className="ml-auto text-xs text-gray-400 dark:text-gray-500">
              {profitPositions.length}종목
            </span>
          </div>
          <TaxPositionTable
            kind="profit"
            positions={profitPositions}
            sellQtyMap={sellQtyMap}
            maxTaxFreeProfit={maxTaxFreeProfit}
            totalLoss={totalLoss}
            hasAnyQtyInput={hasAnyQtyInput}
            handleQtyChange={handleQtyChange}
          />
        </div>
      )}

      {lossPositions.length > 0 && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 dark:border-gray-800">
            <TrendingDown size={14} className="text-blue-400" />
            <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
              손실 종목
            </span>
            <span className="hidden sm:inline text-xs text-gray-400 dark:text-gray-500 ml-1">
              — 매도 시 손익 통산으로 수익 종목 절세 효과
            </span>
            <span className="ml-auto text-xs text-gray-400 dark:text-gray-500">
              {lossPositions.length}종목
            </span>
          </div>
          <TaxPositionTable
            kind="loss"
            positions={lossPositions}
            sellQtyMap={sellQtyMap}
            maxTaxFreeProfit={maxTaxFreeProfit}
            totalLoss={totalLoss}
            hasAnyQtyInput={hasAnyQtyInput}
            handleQtyChange={handleQtyChange}
          />
        </div>
      )}

      {hasAnyQtyInput && (
        <TaxSimulationCard
          totalSimPnl={totalSimPnl}
          alreadyRealized={alreadyRealized}
          simTotalRealized={simTotalRealized}
          simTax={simTax}
          simTaxDiff={simTaxDiff}
          currentTax={currentTax}
        />
      )}

      {!hasAnyQtyInput && recommendations.length > 0 && (
        <TaxRecommendationList recommendations={recommendations} />
      )}

      {profitPositions.length === 0 && lossPositions.length === 0 && (
        <div className="rounded-xl bg-gray-50 dark:bg-gray-800/50 p-4 text-center text-xs text-gray-400 dark:text-gray-500">
          해외 종목 미실현 손익 정보가 없습니다.
        </div>
      )}
    </div>
  );
}
