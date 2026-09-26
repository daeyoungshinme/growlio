import { BadgeCheck, Info, TrendingUp, TrendingDown, Lightbulb, TriangleAlert } from "lucide-react";
import type { OverseasPositionDetail, OverseasRealizedSummary } from "@/api/tax";
import { fmtKrw } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { useTaxSimulation, TAX_DEDUCTION } from "@/hooks/useTaxSimulation";
import { TaxPositionTable } from "./TaxPositionTable";
import { TaxSimulationCard } from "./TaxSimulationCard";
import { TaxRecommendationList } from "./TaxRecommendationList";

interface Props {
  positions: OverseasPositionDetail[];
  /** 증권사 체결 기준 올해 실현손익 자동 집계(E6) — 없거나 자동 집계 계좌가 없으면 수기 입력만 */
  realized?: OverseasRealizedSummary | null;
}

export default function TaxPlannerSection({ positions, realized }: Props) {
  const autoRealized = realized?.realized_gain_krw ?? null;
  const {
    alreadyRealizedInput,
    setAlreadyRealizedInput,
    sellQtyMap,
    alreadyRealized,
    isManualRealized,
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
  } = useTaxSimulation(positions, autoRealized);

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
            <span className="font-medium"> 매매 차익(양도소득)</span>만 계산합니다. 양도차익은
            분류과세라 금융소득 종합과세(이자·배당 연 2,000만원 초과)와 합산되지 않습니다.
          </p>
        </div>

        {autoRealized !== null && realized ? (
          <div className="space-y-1.5" data-testid="auto-realized">
            <div className="flex items-start gap-2">
              <BadgeCheck size={13} className="text-emerald-500 mt-0.5 shrink-0" />
              <p className="text-xs text-gray-600 dark:text-gray-300">
                증권사 체결 기준 올해 실현 손익{" "}
                <span className={`font-semibold ${pnlColor(autoRealized)}`}>
                  {fmtKrw(autoRealized)}
                </span>
                을 자동으로 불러왔어요 (
                {realized.covered_accounts.map((a) => a.account_name).join(", ")}, {realized.as_of}{" "}
                기준).
              </p>
            </div>
            {realized.uncovered_accounts.length > 0 && (
              <div className="flex items-start gap-2">
                <TriangleAlert size={13} className="text-amber-500 mt-0.5 shrink-0" />
                <div className="text-xs text-amber-700 dark:text-amber-400 space-y-0.5">
                  <p>아래 계좌의 실현 손익은 빠져 있어요 — 있다면 합계를 직접 입력하세요.</p>
                  <ul className="list-disc pl-4">
                    {realized.uncovered_accounts.map((a) => (
                      <li key={a.account_id}>
                        {a.account_name}: {a.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-start gap-2">
            <Info size={13} className="text-gray-400 mt-0.5 shrink-0" />
            <p className="text-xs text-gray-500 dark:text-gray-400">
              올해 이미 해외 주식을 매도해 실현한 손익이 있다면 입력하세요 (양도차익만, 배당금
              제외). 없으면 0. 한국투자증권(KIS) 실전 계좌는 자동으로 불러와요.
            </p>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <label
            htmlFor="tax-planner-realized"
            className="text-xs font-medium text-gray-600 dark:text-gray-400 shrink-0"
          >
            {autoRealized !== null ? "직접 입력 (자동값 대신)" : "올해 실현 손익 (원)"}
          </label>
          <input
            id="tax-planner-realized"
            type="text"
            inputMode="numeric"
            value={alreadyRealizedInput}
            onChange={(e) => setAlreadyRealizedInput(e.target.value)}
            placeholder={autoRealized !== null ? String(Math.round(autoRealized)) : "0"}
            className="w-36 min-w-0 min-h-[44px] border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {isManualRealized && alreadyRealized !== 0 && (
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
