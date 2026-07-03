import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { BacktestResult, runBacktest } from "@/api/backtest";
import { fetchPortfolios } from "@/api/portfolios";
import BacktestResultChart from "@/components/backtest/BacktestResultChart";
import BacktestMetricsTable from "@/components/backtest/BacktestMetricsTable";
import SkeletonCard from "@/components/common/SkeletonCard";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { BACKTEST_DEFAULT_END_DATE } from "@/constants/defaults";
import { useBacktestDateRange } from "@/hooks/useBacktestDateRange";
import { QUERY_KEYS } from "@/constants/queryKeys";

export default function BacktestTab() {
  const { data: portfoliosRaw, isLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
  });
  const portfolios = useMemo(
    () => (Array.isArray(portfoliosRaw) ? portfoliosRaw : []),
    [portfoliosRaw],
  );

  const { startDate, endDate, activePreset, setStartDate, setEndDate, setPreset } =
    useBacktestDateRange();

  const [backtestSelectedIds, setBacktestSelectedIds] = useState<Set<string>>(() => new Set());
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [includeSpy, setIncludeSpy] = useState(true);
  const [includeReal, setIncludeReal] = useState(true);
  const [reinvestDividends, setReinvestDividends] = useState(true);

  const runMut = useMutation({
    mutationFn: () =>
      runBacktest({
        portfolio_ids: Array.from(backtestSelectedIds),
        start_date: startDate,
        end_date: endDate,
        include_spy: includeSpy,
        include_real_portfolio: includeReal,
        reinvest_dividends: reinvestDividends,
      }),
    onSuccess: (data) => setBacktestResult(data),
    onError: (e) => toast(extractErrorMessage(e, "백테스트 실행에 실패했습니다"), "error"),
  });

  const canRunBacktest =
    startDate < endDate && (backtestSelectedIds.size > 0 || includeSpy || includeReal);

  if (isLoading) {
    return <SkeletonCard />;
  }

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="space-y-3">
          {portfolios.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs text-gray-400 dark:text-gray-500 font-medium">
                  포트폴리오 선택
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setBacktestSelectedIds(new Set(portfolios.map((p) => p.id)))}
                    className="text-xs text-blue-500 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
                  >
                    전체 선택
                  </button>
                  <button
                    onClick={() => setBacktestSelectedIds(new Set())}
                    className="text-xs text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
                  >
                    전체 해제
                  </button>
                </div>
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                {portfolios.map((p) => (
                  <label
                    key={p.id}
                    className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={backtestSelectedIds.has(p.id)}
                      onChange={(e) => {
                        const next = new Set(backtestSelectedIds);
                        if (e.target.checked) next.add(p.id);
                        else next.delete(p.id);
                        setBacktestSelectedIds(next);
                      }}
                      className="rounded text-blue-600"
                    />
                    {p.name}
                  </label>
                ))}
              </div>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-gray-400 dark:text-gray-500 font-medium mr-1">기간</span>
            {([1, 3, 5, 10] as const).map((y) => (
              <button
                key={y}
                onClick={() => setPreset(y)}
                className={`px-2.5 py-1 text-xs rounded-lg font-medium transition-colors ${
                  activePreset === y
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
                }`}
              >
                {y}년
              </button>
            ))}
            <button
              onClick={() => setPreset(30)}
              className={`px-2.5 py-1 text-xs rounded-lg font-medium transition-colors ${
                activePreset === 30
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
              }`}
            >
              최대
            </button>
          </div>
          <div className="flex flex-wrap gap-3">
            <div>
              <label className="block text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">
                시작일
              </label>
              <input
                type="date"
                value={startDate}
                max={endDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">
                종료일
              </label>
              <input
                type="date"
                value={endDate}
                min={startDate}
                max={BACKTEST_DEFAULT_END_DATE}
                onChange={(e) => setEndDate(e.target.value)}
                className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={includeSpy}
                onChange={(e) => setIncludeSpy(e.target.checked)}
                className="rounded text-blue-600"
              />
              S&P 500 포함
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={includeReal}
                onChange={(e) => setIncludeReal(e.target.checked)}
                className="rounded text-blue-600"
              />
              실제 포트폴리오 포함
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={reinvestDividends}
                onChange={(e) => setReinvestDividends(e.target.checked)}
                className="rounded text-blue-600"
              />
              배당금 재투자
            </label>
          </div>
          <div className="flex justify-end">
            <button
              onClick={() => {
                setBacktestResult(null);
                runMut.mutate();
              }}
              disabled={!canRunBacktest || runMut.isPending}
              aria-busy={runMut.isPending}
              className="w-full md:w-auto px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {runMut.isPending ? "계산 중..." : "▶ 백테스팅 실행"}
            </button>
          </div>
        </div>
        {runMut.isError && (
          <p className="mt-2 text-xs text-red-500">
            백테스팅 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.
          </p>
        )}
      </div>

      {backtestResult && backtestResult.dates.length > 0 && (
        <div className="card space-y-6">
          <BacktestResultChart dates={backtestResult.dates} series={backtestResult.series} />
          <div className="border-t border-gray-100 dark:border-gray-700 pt-4">
            <BacktestMetricsTable metrics={backtestResult.metrics} />
          </div>
        </div>
      )}
      {backtestResult && backtestResult.dates.length === 0 && (
        <div className="card text-center text-sm text-gray-400 dark:text-gray-600 py-8">
          해당 기간의 가격 데이터가 없습니다. 기간을 조정해보세요.
        </div>
      )}
    </div>
  );
}
