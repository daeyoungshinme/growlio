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

function yieldBadgeClass(y: number): string {
  if (y >= 7) return "bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 font-bold";
  if (y >= 4) return "bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400";
  if (y >= 2) return "bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400";
  return "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400";
}

function dividendFreqInfo(months: number[], isManual: boolean): { label: string; cls: string } {
  const n = months.length;
  if (n === 0) return { label: "미설정", cls: "bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500" };
  if (n === 12) return { label: "월배당", cls: "bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400" };
  if (n === 4) return { label: "분기배당", cls: "bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400" };
  if (n === 2) return { label: "반기배당", cls: "bg-orange-50 dark:bg-orange-950 text-orange-600 dark:text-orange-400" };
  if (n === 1) return { label: "연배당", cls: "bg-purple-50 dark:bg-purple-950 text-purple-600 dark:text-purple-400" };
  if (isManual) return { label: `${n}회/년(수동)`, cls: "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400" };
  return { label: `${n}회/년`, cls: "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400" };
}

function weightBarColor(pct: number): string {
  if (pct >= 25) return "bg-amber-400";
  if (pct >= 15) return "bg-blue-400";
  if (pct >= 5) return "bg-emerald-400";
  return "bg-gray-400";
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
            const barColor = weightBarColor(pct);
            const freqInfo = dividendFreqInfo(item.dividend_months ?? [], item.dividend_months_is_manual ?? false);
            return (
              <div key={item.ticker ?? `unclassified-${idx}`} className="px-4 py-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-medium text-gray-900 dark:text-gray-50 truncate text-sm">{item.name}</p>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                      {item.ticker ?? "미분류"}{item.market ? ` · ${item.market}` : ""}
                    </p>
                    {(item.investment_yield ?? 0) > 0 && (
                      <span className={`text-xs px-1.5 py-0.5 rounded-full mt-1 inline-block ${yieldBadgeClass(item.investment_yield)}`}>
                        배당율 {item.investment_yield.toFixed(2)}%
                      </span>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    {item.estimated_annual_krw > 0 ? (
                      <>
                        <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">{fmtKrwShort(item.estimated_annual_krw)}원</p>
                        <div className="flex items-center justify-end gap-1 mt-1">
                          <div className="w-12 bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                            <div className={`${barColor} h-full rounded-full`} style={{ width: `${Math.min(pct, 100)}%` }} />
                          </div>
                          <span className="text-xs text-gray-400 dark:text-gray-500">{pct.toFixed(1)}%</span>
                        </div>
                      </>
                    ) : (
                      <p className="text-xs text-gray-300 dark:text-gray-600">—</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                  <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${freqInfo.cls}`}>{freqInfo.label}</span>
                  {(item.dividend_months ?? []).length > 0 && (item.dividend_months ?? []).length < 12 && (
                    (item.dividend_months ?? []).map((m) => (
                      <span key={m} className="text-xs px-1 py-0 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500">{m}월</span>
                    ))
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
        {!isLoading && items.length > 0 && (
          <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800 flex items-center justify-between">
            <span className="text-sm font-semibold text-gray-500 dark:text-gray-400">합계</span>
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-50">{fmtKrwShort(totalEstimated)}원</span>
          </div>
        )}
      </div>

      {/* 데스크탑 테이블 */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full min-w-[380px] text-xs">
          <thead>
            <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
              <th className="py-2 px-5 text-left text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">종목</th>
              <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">배당율</th>
              <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">배당월</th>
              <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">연간/월 배당</th>
              <th className="py-2 px-5 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">비중</th>
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
                const barColor = weightBarColor(pct);
                const freqInfo = dividendFreqInfo(item.dividend_months ?? [], item.dividend_months_is_manual ?? false);
                return (
                  <tr key={item.ticker ?? `unclassified-${idx}`} className="border-t border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                    <td className="py-2 px-5">
                      <p className="font-medium text-gray-900 dark:text-gray-50">{item.name}</p>
                      {item.ticker && (
                        <p className="text-xs text-gray-400 dark:text-gray-500">{item.ticker}{item.market ? ` · ${item.market}` : ""}</p>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right">
                      {(item.investment_yield ?? 0) > 0 ? (
                        <span className={`text-xs px-1.5 py-0.5 rounded-full ${yieldBadgeClass(item.investment_yield)}`}>
                          {item.investment_yield.toFixed(2)}%
                        </span>
                      ) : (
                        <span className="text-gray-300 dark:text-gray-600">—</span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <div className="flex flex-wrap gap-0.5 justify-end items-center">
                        <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${freqInfo.cls}`}>{freqInfo.label}</span>
                        {(item.dividend_months ?? []).length > 0 && (item.dividend_months ?? []).length < 12 && (
                          (item.dividend_months ?? []).map((m) => (
                            <span key={m} className="text-xs px-1 py-0 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500">{m}월</span>
                          ))
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
                    </td>
                    <td className="py-2 px-3 text-right font-semibold text-gray-900 dark:text-gray-50 whitespace-nowrap">
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
                    <td className="py-2 px-5 text-right">
                      {item.estimated_annual_krw > 0 ? (
                        <div className="flex items-center justify-end gap-1.5">
                          <div className="w-16 bg-gray-100 dark:bg-gray-700 rounded-full h-2.5 overflow-hidden">
                            <div className={`${barColor} h-full rounded-full`} style={{ width: `${Math.min(pct, 100)}%` }} />
                          </div>
                          <span className="text-xs font-medium text-gray-700 dark:text-gray-300 w-10 text-right">{pct.toFixed(1)}%</span>
                        </div>
                      ) : (
                        <span className="text-gray-300 dark:text-gray-600">—</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
          {!isLoading && items.length > 0 && (
            <tfoot>
              <tr className="bg-gray-50 dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 font-semibold text-sm">
                <td className="py-2.5 px-5 text-gray-500 dark:text-gray-400">합계</td>
                <td className="py-2.5 px-3" />
                <td className="py-2.5 px-3" />
                <td className="py-2.5 px-3 text-right text-gray-900 dark:text-gray-50">{fmtKrwShort(totalEstimated)}원</td>
                <td className="py-2.5 px-5 text-right text-gray-500 dark:text-gray-400">100%</td>
              </tr>
            </tfoot>
          )}
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
