import { Calculator } from "lucide-react";
import { fmtKrw } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { TAX_DEDUCTION } from "@/hooks/useTaxSimulation";

interface Props {
  totalSimPnl: number;
  alreadyRealized: number;
  simTotalRealized: number;
  simTax: number;
  simTaxDiff: number;
  currentTax: number;
}

export function TaxSimulationCard({
  totalSimPnl,
  alreadyRealized,
  simTotalRealized,
  simTax,
  simTaxDiff,
  currentTax,
}: Props) {
  return (
    <div
      className={`rounded-xl border p-3 sm:p-4 space-y-3 ${
        simTax === 0
          ? "border-emerald-200 dark:border-emerald-800/50 bg-emerald-50 dark:bg-emerald-900/20"
          : "border-orange-200 dark:border-orange-800/50 bg-orange-50 dark:bg-orange-900/20"
      }`}
    >
      <div className="flex items-center gap-2">
        <Calculator size={13} className={simTax === 0 ? "text-emerald-500" : "text-orange-500"} />
        <span
          className={`text-xs font-semibold ${simTax === 0 ? "text-emerald-700 dark:text-emerald-400" : "text-orange-700 dark:text-orange-400"}`}
        >
          매도 시뮬레이션 합계
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-2 sm:gap-x-6 sm:gap-y-1.5 text-xs">
        <span className="text-gray-500 dark:text-gray-400">선택 종목 실현 손익</span>
        <span className={`text-right font-medium ${pnlColor(totalSimPnl)}`}>
          {fmtKrw(totalSimPnl)}
        </span>
        {alreadyRealized !== 0 && (
          <>
            <span className="text-gray-500 dark:text-gray-400">기존 실현 손익</span>
            <span className={`text-right font-medium ${pnlColor(alreadyRealized)}`}>
              {fmtKrw(alreadyRealized)}
            </span>
          </>
        )}
        <span className="text-gray-500 dark:text-gray-400">통산 실현 손익</span>
        <span className={`text-right font-medium ${pnlColor(simTotalRealized)}`}>
          {fmtKrw(simTotalRealized)}
        </span>
        <span className="text-gray-500 dark:text-gray-400">250만원 공제</span>
        <span className="text-right text-gray-600 dark:text-gray-300">
          −{fmtKrw(Math.min(TAX_DEDUCTION, Math.max(0, simTotalRealized)))}
        </span>
        <span
          className={`font-semibold ${simTax === 0 ? "text-emerald-600 dark:text-emerald-400" : "text-orange-600 dark:text-orange-400"}`}
        >
          예상 납부 세금
        </span>
        <span
          className={`text-right font-bold text-base ${simTax === 0 ? "text-emerald-600 dark:text-emerald-400" : "text-orange-600 dark:text-orange-400"}`}
        >
          {fmtKrw(simTax)}
        </span>
        {simTaxDiff !== 0 && currentTax > 0 && (
          <>
            <span className="text-gray-400 dark:text-gray-500">기존 대비 세금 변화</span>
            <span className={`text-right font-medium ${pnlColor(-simTaxDiff)}`}>
              {simTaxDiff > 0 ? "+" : ""}
              {fmtKrw(simTaxDiff)}
            </span>
          </>
        )}
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-500">
        * 미실현 손익 기준 추정치. 22% 세율(지방소득세 포함). 실제 매도가는 다를 수 있습니다.
      </p>
    </div>
  );
}
