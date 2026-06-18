import { memo, useCallback, useState } from "react";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import {
  TickerDividendItem,
  updateTickerDividendMonths,
  deleteTickerDividendMonths,
} from "@/api/dashboard";
import DividendMonthsModal from "./DividendMonthsModal";
import { fmtKrwShort } from "@/utils/format";
import { toast } from "@/utils/toast";
import { dividendFreqInfo, weightBarColor, yieldBadgeClass } from "@/utils/dividendUtils";
import { QUERY_KEYS } from "@/constants/queryKeys";

interface Props {
  items: TickerDividendItem[];
  isLoading: boolean;
}

function SkeletonCard() {
  return (
    <div className="px-4 py-3 animate-pulse">
      <div className="flex justify-between mb-1.5">
        <div className="h-3.5 w-32 bg-gray-100 dark:bg-gray-800 rounded" />
        <div className="h-3.5 w-16 bg-gray-100 dark:bg-gray-800 rounded" />
      </div>
      <div className="flex justify-between mb-2">
        <div className="h-3 w-24 bg-gray-100 dark:bg-gray-800 rounded" />
        <div className="h-3 w-20 bg-gray-100 dark:bg-gray-800 rounded" />
      </div>
      <div className="border-t border-gray-100 dark:border-gray-800 my-2" />
      <div className="flex gap-1">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-5 w-10 bg-gray-100 dark:bg-gray-800 rounded-full" />
        ))}
      </div>
    </div>
  );
}

interface EditTarget {
  ticker: string;
  market: string;
  name: string;
  currentMonths: number[];
  isManual: boolean;
}

const DividendByTickerTable = memo(function DividendByTickerTable({ items, isLoading }: Props) {
  const qc = useQueryClient();
  const [editTarget, setEditTarget] = useState<EditTarget | null>(null);
  const totalEstimated = items.reduce((s, d) => s + d.estimated_annual_krw, 0);

  const saveMutation = useMutation({
    mutationFn: ({
      ticker,
      market,
      months,
    }: {
      ticker: string;
      market: string;
      months: number[];
    }) => updateTickerDividendMonths(ticker, market, months),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendByTicker });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard });
      setEditTarget(null);
    },
    onError: () => toast("배당월 저장에 실패했습니다"),
  });

  const resetMutation = useMutation({
    mutationFn: ({ ticker, market }: { ticker: string; market: string }) =>
      deleteTickerDividendMonths(ticker, market),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendByTicker });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard });
      setEditTarget(null);
    },
    onError: () => toast("배당월 초기화에 실패했습니다"),
  });

  const isSaving = saveMutation.isPending || resetMutation.isPending;

  const handleEditClick = useCallback((item: TickerDividendItem) => {
    setEditTarget({
      ticker: item.ticker!,
      market: item.market ?? "",
      name: item.name,
      currentMonths: item.dividend_months,
      isManual: item.dividend_months_is_manual,
    });
  }, []);

  return (
    <div>
      <div className="divide-y divide-gray-100 dark:divide-gray-700">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
        ) : items.length === 0 ? (
          <div className="py-6 text-center text-xs text-gray-300 dark:text-gray-600">
            보유 종목 없음
          </div>
        ) : (
          items.map((item, idx) => {
            const pct = totalEstimated > 0 ? (item.estimated_annual_krw / totalEstimated) * 100 : 0;
            const barColor = weightBarColor(pct);
            const freqInfo = dividendFreqInfo(
              item.dividend_months ?? [],
              item.dividend_months_is_manual ?? false,
            );
            const months = item.dividend_months ?? [];

            return (
              <div key={item.ticker ?? `unclassified-${idx}`} className="px-4 py-3">
                {/* Row 1: 종목명 + 연간 배당액 */}
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold text-sm text-gray-900 dark:text-gray-50 truncate">
                    {item.name}
                  </p>
                  <span className="text-sm font-semibold text-gray-900 dark:text-gray-50 shrink-0 whitespace-nowrap">
                    {item.estimated_annual_krw > 0
                      ? `${fmtKrwShort(item.estimated_annual_krw)}원`
                      : "—"}
                  </span>
                </div>

                {/* Row 2: 티커·마켓 + 배당율 배지 | 비중 바 + % */}
                <div className="flex items-center justify-between mt-0.5 gap-2">
                  <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
                    <span className="text-xs text-gray-400 dark:text-gray-500 truncate">
                      {item.ticker ?? "미분류"}
                      {item.market ? ` · ${item.market}` : ""}
                    </span>
                    {(item.investment_yield ?? 0) > 0 && (
                      <span
                        className={`text-xs px-1.5 py-0.5 rounded-full ${yieldBadgeClass(item.investment_yield)}`}
                      >
                        {item.investment_yield.toFixed(2)}%
                      </span>
                    )}
                  </div>
                  {item.estimated_annual_krw > 0 && (
                    <div className="flex items-center gap-1.5 shrink-0">
                      <div className="w-14 bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                        <div
                          className={`${barColor} h-full rounded-full`}
                          style={{ width: `${Math.min(pct, 100)}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500 dark:text-gray-400 w-9 text-right">
                        {pct.toFixed(1)}%
                      </span>
                    </div>
                  )}
                </div>

                {/* 구분선 */}
                <div className="border-t border-gray-100 dark:border-gray-700 my-2" />

                {/* Row 3: 빈도 배지 + 월 배지들 + 편집 버튼 */}
                <div className="flex items-center gap-1 flex-wrap">
                  <span
                    className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${freqInfo.cls}`}
                  >
                    {freqInfo.label}
                  </span>
                  {months.length > 0 &&
                    months.length < 12 &&
                    months.map((m) => (
                      <span
                        key={m}
                        className="text-xs px-1.5 py-0.5 rounded-full bg-slate-200 dark:bg-slate-600 text-slate-600 dark:text-slate-100"
                      >
                        {m}월
                      </span>
                    ))}
                  {item.ticker && (
                    <button
                      onClick={() => handleEditClick(item)}
                      className="p-0.5 text-gray-300 dark:text-gray-600 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950 rounded transition-colors"
                      title="배당월 수정"
                    >
                      <Pencil size={11} />
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
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-50">
              {fmtKrwShort(totalEstimated)}원
            </span>
          </div>
        )}
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
});

export default DividendByTickerTable;
