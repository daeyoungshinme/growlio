import { memo } from "react";
import { fmtKrwShort } from "@/utils/format";
import SkeletonStatBox from "@/components/common/SkeletonStatBox";

interface Props {
  annualReceived: number | null;
  estimatedAnnual: number | null;
  estimatedMonthly: number | null;
  overallDividendYield?: number | null;
  isLoading?: boolean;
}

export default memo(function DividendSection({
  annualReceived,
  estimatedAnnual,
  estimatedMonthly,
  overallDividendYield,
  isLoading,
}: Props) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-3 divide-x divide-gray-100 dark:divide-gray-800">
        {[0, 1, 2].map((i) => (
          <div key={i} className="px-2 py-3 sm:px-4 text-center">
            <SkeletonStatBox />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 divide-x divide-gray-100 dark:divide-gray-800">
      <div className="px-2 py-3 sm:px-4 text-center min-w-0">
        <p className="text-xs tracking-wide uppercase font-semibold text-gray-400 dark:text-gray-500 leading-tight whitespace-nowrap">
          연간 배당금
        </p>
        <p className="text-sm sm:text-lg font-bold mt-1 leading-tight text-green-600 truncate">
          {estimatedAnnual != null && estimatedAnnual > 0 ? (
            <>
              {fmtKrwShort(estimatedAnnual)}원
              {overallDividendYield != null && (
                <span className="text-xs sm:text-sm font-semibold ml-0.5">
                  ({overallDividendYield.toFixed(2)}%)
                </span>
              )}
            </>
          ) : (
            "—"
          )}
        </p>
      </div>
      <div className="px-2 py-3 sm:px-4 text-center min-w-0">
        <p className="text-xs tracking-wide uppercase font-semibold text-gray-400 dark:text-gray-500 leading-tight whitespace-nowrap">
          실제 배당금
        </p>
        <p className="text-base sm:text-lg font-bold mt-1 leading-tight text-gray-900 dark:text-gray-50 truncate">
          {annualReceived != null && annualReceived > 0 ? `${fmtKrwShort(annualReceived)}원` : "—"}
        </p>
      </div>
      <div className="px-2 py-3 sm:px-4 text-center min-w-0">
        <p className="text-xs tracking-wide uppercase font-semibold text-gray-400 dark:text-gray-500 leading-tight whitespace-nowrap">
          월별 배당금
        </p>
        <p className="text-base sm:text-lg font-bold mt-1 leading-tight text-blue-600 truncate">
          {estimatedMonthly != null && estimatedMonthly > 0
            ? `${fmtKrwShort(estimatedMonthly)}원`
            : "—"}
        </p>
      </div>
    </div>
  );
});
