import { Info, FlaskConical } from "lucide-react";
import { fmtKrw } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import type { GeumtSimulation } from "@/api/tax";

interface Props {
  sim: GeumtSimulation;
  currentOverseasTax: number;
}

export function GeumtSimulationSection({ sim, currentOverseasTax }: Props) {
  const hasGain = sim.overseas_gain_krw > 0 || sim.domestic_gain_krw > 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 pt-3 border-t border-gray-100 dark:border-gray-700">
        <FlaskConical size={14} className="text-violet-500 shrink-0" />
        <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
          금투세 시뮬레이션
        </span>
        <span className="text-xs px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-900/40 text-violet-600 dark:text-violet-300 font-medium">
          유예 중
        </span>
      </div>

      <div className="flex items-start gap-2 p-2.5 bg-violet-50 dark:bg-violet-900/20 rounded-lg">
        <Info size={12} className="text-violet-500 mt-0.5 shrink-0" />
        <p className="text-xs text-violet-700 dark:text-violet-300 leading-relaxed">
          금융투자소득세(금투세)는 2025년 이후 유예 중입니다. 시행 시{" "}
          <span className="font-medium">국내 주식 5천만원·해외 주식 250만원 공제 후 20%</span>(3억
          초과분 25%)가 적용됩니다. 현재 미실현 손익 기준 추정치입니다.
        </p>
      </div>

      {!hasGain ? (
        <p className="text-xs text-gray-400 dark:text-gray-500 text-center py-2">
          보유 주식 미실현 손익이 없습니다.
        </p>
      ) : (
        <div className="rounded-xl border border-violet-200 dark:border-violet-800/50 bg-white dark:bg-gray-900 overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-violet-50 dark:bg-violet-900/20">
                <th className="text-left px-3 py-2 text-violet-600 dark:text-violet-400 font-medium">
                  구분
                </th>
                <th className="text-right px-3 py-2 text-violet-600 dark:text-violet-400 font-medium">
                  국내 주식
                </th>
                <th className="text-right px-3 py-2 text-violet-600 dark:text-violet-400 font-medium">
                  해외 주식
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              <tr>
                <td className="px-3 py-2 text-gray-500 dark:text-gray-400">미실현 손익</td>
                <td
                  className={`px-3 py-2 text-right font-medium ${pnlColor(sim.domestic_gain_krw)}`}
                >
                  {fmtKrw(sim.domestic_gain_krw)}
                </td>
                <td
                  className={`px-3 py-2 text-right font-medium ${pnlColor(sim.overseas_gain_krw)}`}
                >
                  {fmtKrw(sim.overseas_gain_krw)}
                </td>
              </tr>
              <tr>
                <td className="px-3 py-2 text-gray-500 dark:text-gray-400">기본공제</td>
                <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-300">
                  −{fmtKrw(sim.domestic_deduction_krw)}
                </td>
                <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-300">
                  −{fmtKrw(sim.overseas_deduction_krw)}
                </td>
              </tr>
              <tr>
                <td className="px-3 py-2 text-gray-500 dark:text-gray-400">과세 표준</td>
                <td
                  className={`px-3 py-2 text-right font-medium ${pnlColor(sim.domestic_taxable_krw)}`}
                >
                  {fmtKrw(sim.domestic_taxable_krw)}
                </td>
                <td
                  className={`px-3 py-2 text-right font-medium ${pnlColor(sim.overseas_taxable_krw)}`}
                >
                  {fmtKrw(sim.overseas_taxable_krw)}
                </td>
              </tr>
              <tr className="bg-violet-50/50 dark:bg-violet-900/10">
                <td className="px-3 py-2 font-semibold text-violet-700 dark:text-violet-400">
                  금투세(추정)
                </td>
                <td className="px-3 py-2 text-right font-bold text-violet-700 dark:text-violet-400">
                  {fmtKrw(sim.domestic_tax_krw)}
                </td>
                <td className="px-3 py-2 text-right font-bold text-violet-700 dark:text-violet-400">
                  {fmtKrw(sim.overseas_tax_krw)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {hasGain && (
        <div className="flex items-center justify-between px-3 py-2.5 rounded-lg bg-gray-50 dark:bg-gray-800 text-xs">
          <div className="space-y-0.5">
            <p className="text-gray-500 dark:text-gray-400">
              금투세 합계{" "}
              <span className="font-semibold text-violet-600 dark:text-violet-400">
                {fmtKrw(sim.total_tax_krw)}
              </span>
            </p>
            <p className="text-gray-400 dark:text-gray-500">
              현행 세제 기준 {fmtKrw(currentOverseasTax)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-gray-500 dark:text-gray-400">현행 대비</p>
            <p className={`font-bold ${pnlColor(-sim.tax_difference_krw)}`}>
              {sim.tax_difference_krw > 0 ? "+" : ""}
              {fmtKrw(sim.tax_difference_krw)}
            </p>
          </div>
        </div>
      )}

      <p className="text-xs text-gray-400 dark:text-gray-500">
        세율: 기본 {sim.rates.standard_pct}% / 3억 초과 {sim.rates.excess_above_300m_pct}%
      </p>
    </div>
  );
}
