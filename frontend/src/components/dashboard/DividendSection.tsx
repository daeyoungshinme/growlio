import { fmtKrwShort } from "../../utils/format";

interface Props {
  annualReceived: number | null;
  estimatedAnnual: number | null;
  estimatedMonthly: number | null;
  overallDividendYield?: number | null;
}

export default function DividendSection({ annualReceived, estimatedAnnual, estimatedMonthly, overallDividendYield }: Props) {
  return (
    <div className="grid grid-cols-3 divide-x divide-gray-100 dark:divide-gray-800">
      <div className="px-4 py-3 sm:px-5">
        <p className="text-[11px] tracking-wide uppercase font-semibold text-gray-400 dark:text-gray-500">예상 연간 배당금</p>
        <p className="text-base sm:text-lg font-bold mt-1 leading-tight text-green-600">
          {estimatedAnnual != null && estimatedAnnual > 0 ? (
            <>
              {fmtKrwShort(estimatedAnnual)}원
              {overallDividendYield != null && (
                <span className="text-sm font-semibold ml-1">({overallDividendYield.toFixed(2)}%)</span>
              )}
            </>
          ) : "—"}
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">배당수익률 기준 추정</p>
      </div>
      <div className="px-4 py-3 sm:px-5">
        <p className="text-[11px] tracking-wide uppercase font-semibold text-gray-400 dark:text-gray-500">올해 수령 배당금</p>
        <p className="text-base sm:text-lg font-bold mt-1 leading-tight text-gray-900 dark:text-gray-50">
          {annualReceived != null && annualReceived > 0 ? `${fmtKrwShort(annualReceived)}원` : "—"}
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
          {annualReceived != null && annualReceived > 0 ? "실제 수령 합계" : "배당 내역을 입력해주세요"}
        </p>
      </div>
      <div className="px-4 py-3 sm:px-5">
        <p className="text-[11px] tracking-wide uppercase font-semibold text-gray-400 dark:text-gray-500">월평균 예상 배당금</p>
        <p className="text-base sm:text-lg font-bold mt-1 leading-tight text-blue-600">
          {estimatedMonthly != null && estimatedMonthly > 0 ? `${fmtKrwShort(estimatedMonthly)}원` : "—"}
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">연간 예상 배당금 ÷ 12</p>
      </div>
    </div>
  );
}
