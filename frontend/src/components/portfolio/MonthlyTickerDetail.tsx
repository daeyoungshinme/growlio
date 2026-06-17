import { fmtKrw, fmtKrwShort } from "@/utils/format";
import { MONTH_LABELS } from "@/utils/dividendUtils";
import type { DividendByTicker } from "@/types";

interface MonthlyActual {
  month: string;
  amount: number;
}

interface Props {
  selectedMonth: number;
  selectedMonthTickers: DividendByTicker[];
  selectedMonthActual: MonthlyActual | undefined;
  monthStr: string;
  monthlyEstimate: number;
  monthTickerActualMap: Record<string, number>;
}

function sortByMonthlyAmount(items: DividendByTicker[]): DividendByTicker[] {
  return [...items].sort((a, b) => {
    const aCount = a.dividend_months.length > 0 ? a.dividend_months.length : 12;
    const bCount = b.dividend_months.length > 0 ? b.dividend_months.length : 12;
    return (
      Math.round(b.estimated_annual_krw / bCount) - Math.round(a.estimated_annual_krw / aCount)
    );
  });
}

export default function MonthlyTickerDetail({
  selectedMonth,
  selectedMonthTickers,
  selectedMonthActual,
  monthStr,
  monthlyEstimate,
  monthTickerActualMap,
}: Props) {
  const sorted = sortByMonthlyAmount(selectedMonthTickers);

  return (
    <div className="card-overflow">
      <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
        <h3 className="font-semibold text-gray-800 dark:text-gray-200">
          {MONTH_LABELS[selectedMonth - 1]} 배당 종목
          {selectedMonthActual && selectedMonthActual.amount > 0 ? (
            <span className="ml-2 text-xs font-normal text-green-600 dark:text-green-400">
              실수령 {fmtKrwShort(selectedMonthActual.amount)}원
            </span>
          ) : monthlyEstimate > 0 ? (
            <span className="ml-2 text-xs font-normal text-gray-400 dark:text-gray-500">
              예상 {fmtKrwShort(monthlyEstimate)}원
            </span>
          ) : null}
        </h3>
        <span className="text-xs text-gray-400 dark:text-gray-500">
          {selectedMonthTickers.length}개 종목
        </span>
      </div>

      {sorted.length > 0 ? (
        <>
          {/* 모바일 카드 뷰 */}
          <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700">
            {sorted.map((d) => {
              const payCount = d.dividend_months.length > 0 ? d.dividend_months.length : 12;
              const payAmt = Math.round(d.estimated_annual_krw / payCount);
              const usdPerPayment =
                d.estimated_monthly_usd != null ? (d.estimated_monthly_usd * 12) / payCount : null;
              const actualAmt = monthTickerActualMap[`${monthStr}-${d.ticker ?? ""}`];
              return (
                <div key={`${d.ticker}-${d.market}`} className="px-4 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium text-gray-900 dark:text-gray-50 truncate text-sm">
                        {d.name}
                      </p>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                        {d.ticker} · {d.market}
                        {d.investment_yield > 0 && ` · ${d.investment_yield.toFixed(2)}%`}
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      {actualAmt && actualAmt > 0 ? (
                        <p className="font-medium text-green-600 dark:text-green-400 text-sm">
                          수령 {fmtKrw(actualAmt)}
                        </p>
                      ) : d.currency === "USD" && usdPerPayment != null && usdPerPayment > 0 ? (
                        <p className="text-sm text-gray-500 dark:text-gray-400">{fmtKrw(payAmt)}</p>
                      ) : payAmt > 0 ? (
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          예상 {fmtKrw(payAmt)}
                        </p>
                      ) : (
                        <p className="text-sm text-gray-300 dark:text-gray-600">—</p>
                      )}
                      <span
                        className={`text-xs px-1.5 py-0 rounded-full ${
                          d.dividend_months_is_manual
                            ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
                            : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
                        }`}
                      >
                        {d.dividend_months_is_manual ? "수동" : "자동"}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* 데스크탑 테이블 */}
          <div className="hidden sm:block overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
                  <th className="py-2 px-5 text-left text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">
                    종목
                  </th>
                  <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">
                    투자배당수익율
                  </th>
                  <th className="py-2 px-4 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">
                    배당금
                  </th>
                  <th className="py-2 px-5 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">
                    배당월 설정
                  </th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((d) => {
                  const payCount = d.dividend_months.length > 0 ? d.dividend_months.length : 12;
                  const payAmt = Math.round(d.estimated_annual_krw / payCount);
                  const usdPerPayment =
                    d.estimated_monthly_usd != null
                      ? (d.estimated_monthly_usd * 12) / payCount
                      : null;
                  const actualAmt = monthTickerActualMap[`${monthStr}-${d.ticker ?? ""}`];
                  return (
                    <tr
                      key={`${d.ticker}-${d.market}`}
                      className="border-t border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                      <td className="py-2 px-5">
                        <p className="font-medium text-gray-900 dark:text-gray-50">{d.name}</p>
                        <p className="text-xs text-gray-400 dark:text-gray-500">
                          {d.ticker} · {d.market}
                        </p>
                      </td>
                      <td className="py-2 px-3 text-right font-medium text-green-600 dark:text-green-400">
                        {d.investment_yield > 0 ? `${d.investment_yield.toFixed(2)}%` : "—"}
                      </td>
                      <td className="py-2 px-4 text-right">
                        {actualAmt && actualAmt > 0 ? (
                          <span className="font-medium text-green-600 dark:text-green-400">
                            수령 {fmtKrw(actualAmt)}
                          </span>
                        ) : d.currency === "USD" && usdPerPayment != null && usdPerPayment > 0 ? (
                          <span className="text-gray-500 dark:text-gray-400">
                            {fmtKrw(payAmt)}(${usdPerPayment.toFixed(2)})
                          </span>
                        ) : payAmt > 0 ? (
                          <span className="text-gray-500 dark:text-gray-400">
                            예상 {fmtKrw(payAmt)}
                          </span>
                        ) : (
                          <span className="text-gray-300 dark:text-gray-600">—</span>
                        )}
                      </td>
                      <td className="py-2 px-5 text-right">
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full ${
                            d.dividend_months_is_manual
                              ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
                              : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
                          }`}
                        >
                          {d.dividend_months_is_manual ? "수동" : "자동"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-8">
          이 달에 배당 예정 종목이 없습니다.
        </p>
      )}
    </div>
  );
}
