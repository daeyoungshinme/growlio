import { useState } from "react";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { TickerDividendItem, updateTickerDividendMonths, deleteTickerDividendMonths } from "../../api/dashboard";
import DividendMonthsModal from "./DividendMonthsModal";
import { fmtKrwShort } from "../../utils/format";
import { toast } from "../../utils/toast";

interface Props {
  items: TickerDividendItem[];
  isLoading: boolean;
}

function MonthBadges({ months, isManual }: { months: number[] | undefined; isManual: boolean }) {
  if (!months || months.length === 0) return <span className="text-gray-300 dark:text-gray-600">—</span>;
  if (months.length === 12) {
    return (
      <span className="text-xs px-1.5 py-0 rounded-full bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 font-medium">
        월배당
      </span>
    );
  }
  const visible = months.slice(0, 4);
  const rest = months.length - visible.length;
  return (
    <div className="flex flex-nowrap gap-0.5 justify-end">
      {visible.map((m) => (
        <span
          key={m}
          className={`text-xs px-1.5 py-0 rounded-full ${
            isManual
              ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
              : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
          }`}
        >
          {m}
        </span>
      ))}
      {rest > 0 && (
        <span className="text-xs px-1.5 py-0 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500">+{rest}</span>
      )}
    </div>
  );
}

function SkeletonRow() {
  return (
    <tr className="border-b border-gray-50 dark:border-gray-800">
      {[1, 2, 3, 4, 5].map((i) => (
        <td key={i} className="py-2.5 px-3">
          <div className="h-3.5 bg-gray-100 dark:bg-gray-800 rounded animate-pulse" />
        </td>
      ))}
    </tr>
  );
}

interface EditTarget {
  ticker: string;
  market: string;
  name: string;
  currentMonths: number[];
  isManual: boolean;
}

export default function DividendByTickerTable({ items, isLoading }: Props) {
  const qc = useQueryClient();
  const [editTarget, setEditTarget] = useState<EditTarget | null>(null);
  const totalEstimated = items.reduce((s, d) => s + d.estimated_annual_krw, 0);

  const saveMutation = useMutation({
    mutationFn: ({ ticker, market, months }: { ticker: string; market: string; months: number[] }) =>
      updateTickerDividendMonths(ticker, market, months),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dividend-by-ticker"] });
      setEditTarget(null);
    },
    onError: () => toast("배당월 저장에 실패했습니다"),
  });

  const resetMutation = useMutation({
    mutationFn: ({ ticker, market }: { ticker: string; market: string }) =>
      deleteTickerDividendMonths(ticker, market),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dividend-by-ticker"] });
      setEditTarget(null);
    },
    onError: () => toast("배당월 초기화에 실패했습니다"),
  });

  const isSaving = saveMutation.isPending || resetMutation.isPending;

  return (
    <div>
      <p className="text-xs text-gray-400 dark:text-gray-500 mb-2 font-medium">종목별 배당 현황</p>

      {/* 모바일 카드 뷰 */}
      <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700">
        {isLoading ? (
          <div className="py-6 text-center text-xs text-gray-300 dark:text-gray-600">로딩 중...</div>
        ) : items.length === 0 ? (
          <div className="py-6 text-center text-xs text-gray-300 dark:text-gray-600">보유 종목 없음</div>
        ) : (
          items.map((item, idx) => {
            const pct = totalEstimated > 0 ? (item.estimated_annual_krw / totalEstimated) * 100 : 0;
            return (
              <div key={item.ticker ?? `unclassified-${idx}`} className="py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-medium text-gray-800 dark:text-gray-200 truncate text-xs">{item.name}</p>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                      {item.ticker ?? "미분류"}
                      {(item.investment_yield ?? 0) > 0 && ` · 배당율 ${item.investment_yield.toFixed(2)}%`}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    {item.estimated_annual_krw > 0 ? (
                      <>
                        <p className="text-xs font-medium text-green-600 dark:text-green-400">{fmtKrwShort(item.estimated_annual_krw)}원</p>
                        <p className="text-xs text-gray-400 dark:text-gray-500">
                          {item.currency === "USD" && item.estimated_monthly_usd != null
                            ? `$${item.estimated_monthly_usd.toFixed(2)}/월`
                            : `월 ${fmtKrwShort(item.estimated_monthly_krw)}원`}
                        </p>
                      </>
                    ) : (
                      <p className="text-xs text-gray-300 dark:text-gray-600">—</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                  <MonthBadges months={item.dividend_months ?? []} isManual={item.dividend_months_is_manual ?? false} />
                  {item.estimated_annual_krw > 0 && (
                    <span className="text-xs text-gray-400 dark:text-gray-500">비중 {pct.toFixed(1)}%</span>
                  )}
                  {item.ticker && (
                    <button
                      onClick={() =>
                        setEditTarget({
                          ticker: item.ticker!,
                          market: item.market ?? "",
                          name: item.name,
                          currentMonths: item.dividend_months,
                          isManual: item.dividend_months_is_manual,
                        })
                      }
                      className="p-0.5 text-gray-300 dark:text-gray-600 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950 rounded transition-colors"
                      title="배당월 수정"
                    >
                      <Pencil size={10} />
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* 데스크탑 테이블 */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full min-w-[380px] text-xs">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-700">
              <th className="py-1.5 px-2 text-left text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">종목</th>
              <th className="py-1.5 px-2 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">배당율</th>
              <th className="py-1.5 px-2 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">배당월</th>
              <th className="py-1.5 px-2 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">연간/월 배당</th>
              <th className="py-1.5 px-2 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">비중</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-6 text-center text-xs text-gray-300 dark:text-gray-600">
                  보유 종목 없음
                </td>
              </tr>
            ) : (
              items.map((item, idx) => {
                const pct = totalEstimated > 0
                  ? (item.estimated_annual_krw / totalEstimated) * 100
                  : 0;
                return (
                  <tr key={item.ticker ?? `unclassified-${idx}`} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                    <td className="py-2 px-2">
                      <span className="font-medium text-gray-800 dark:text-gray-200">{item.name}</span>
                      {item.ticker && (
                        <span className="ml-1 text-gray-400 dark:text-gray-500">{item.ticker}</span>
                      )}
                    </td>
                    <td className="py-2 px-2 text-right font-medium text-green-600 dark:text-green-400 whitespace-nowrap">
                      {(item.investment_yield ?? 0) > 0 ? `${item.investment_yield.toFixed(2)}%` : "—"}
                    </td>
                    <td className="py-2 px-2 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <MonthBadges months={item.dividend_months ?? []} isManual={item.dividend_months_is_manual ?? false} />
                        {item.ticker && (
                          <button
                            onClick={() =>
                              setEditTarget({
                                ticker: item.ticker!,
                                market: item.market ?? "",
                                name: item.name,
                                currentMonths: item.dividend_months,
                                isManual: item.dividend_months_is_manual,
                              })
                            }
                            className="p-0.5 text-gray-300 dark:text-gray-600 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950 rounded transition-colors"
                            title="배당월 수정"
                          >
                            <Pencil size={10} />
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="py-2 px-2 text-right font-medium text-green-600 dark:text-green-400 whitespace-nowrap">
                      {item.estimated_annual_krw > 0 ? (
                        <div className="flex flex-col items-end gap-0.5">
                          <span>{fmtKrwShort(item.estimated_annual_krw)}원</span>
                          <span className="text-xs font-normal text-gray-400 dark:text-gray-500">
                            {item.currency === "USD" && item.estimated_monthly_usd != null
                              ? `$${item.estimated_monthly_usd.toFixed(2)} · 월 ${fmtKrwShort(item.estimated_monthly_krw)}원`
                              : `월 ${fmtKrwShort(item.estimated_monthly_krw)}원`}
                          </span>
                        </div>
                      ) : "—"}
                    </td>
                    <td className="py-2 px-2 text-right text-gray-500 dark:text-gray-400 whitespace-nowrap">
                      {item.estimated_annual_krw > 0 ? `${pct.toFixed(1)}%` : "—"}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {editTarget && (
        <DividendMonthsModal
          ticker={editTarget.ticker}
          market={editTarget.market}
          name={editTarget.name}
          currentMonths={editTarget.currentMonths}
          isManual={editTarget.isManual}
          onClose={() => setEditTarget(null)}
          onSave={(months) =>
            saveMutation.mutate({ ticker: editTarget.ticker, market: editTarget.market, months })
          }
          onReset={() =>
            resetMutation.mutate({ ticker: editTarget.ticker, market: editTarget.market })
          }
          isSaving={isSaving}
        />
      )}
    </div>
  );
}
