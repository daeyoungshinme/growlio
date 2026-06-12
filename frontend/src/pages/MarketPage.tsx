import { useState } from "react";
import { BarChart2, RefreshCw } from "lucide-react";
import { useThemeStore } from "@/stores/themeStore";
import {
  useEconomicIndicators,
  useIndicatorCalendar,
  useIndicatorHistory,
  useSubscribeMutation,
} from "@/hooks/useEconomicIndicators";
import IndicatorCard from "@/components/market/IndicatorCard";
import EconomicCalendarList from "@/components/market/EconomicCalendarList";
import IndicatorHistoryChart from "@/components/market/IndicatorHistoryChart";
import SkeletonCard from "@/components/common/SkeletonCard";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";

export default function MarketPage() {
  const { isDark } = useThemeStore();
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [historyMonths] = useState(24);

  const { data: indicators = [], isLoading, isError, refetch, isFetching } = useEconomicIndicators();
  const { data: calendar = [], isLoading: isCalendarLoading } = useIndicatorCalendar();
  const { data: history = [], isLoading: isHistoryLoading } = useIndicatorHistory(
    selectedCode ?? "",
    historyMonths,
  );
  const { subscribe, unsubscribe } = useSubscribeMutation();

  const selectedIndicator = indicators.find((ind) => ind.code === selectedCode) ?? null;

  const handleToggleSubscribe = async (code: string, subscribed: boolean) => {
    try {
      if (subscribed) {
        await unsubscribe.mutateAsync(code);
        toast("알림 구독을 해제했습니다.", "success");
      } else {
        await subscribe.mutateAsync(code);
        toast("발표 시 이메일 알림을 받습니다.", "success");
      }
    } catch (e) {
      toast(extractErrorMessage(e, "구독 처리 중 오류가 발생했습니다."), "error");
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 pb-24 lg:pb-6 space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart2 size={22} className="text-blue-600 dark:text-blue-400" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-50">시장 지표</h1>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          aria-label="새로고침"
          className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw size={16} className={isFetching ? "animate-spin" : ""} />
        </button>
      </div>

      {/* 증시 캘린더 */}
      <section
        aria-label="경제 이벤트 발표 일정"
        className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-5"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-gray-800 dark:text-gray-200">
            증시 캘린더
            <span className="ml-2 text-xs font-normal text-gray-400 dark:text-gray-500">향후 90일</span>
          </h2>
        </div>
        {isCalendarLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-14 bg-gray-100 dark:bg-gray-700 rounded-xl animate-pulse" />
            ))}
          </div>
        ) : (
          <EconomicCalendarList events={calendar} />
        )}
      </section>

      {/* 지표 카드 그리드 */}
      <section aria-label="미국 경제지표">
        <h2 className="font-semibold text-gray-800 dark:text-gray-200 mb-3">주요 지표 현황</h2>
        {isLoading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : isError ? (
          <div className="text-center py-8 text-gray-400 dark:text-gray-500 text-sm">
            지표 데이터를 불러오는 중 오류가 발생했습니다.
            <br />
            <button onClick={() => refetch()} className="mt-2 text-blue-500 hover:underline">
              다시 시도
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {indicators.map((ind) => (
              <IndicatorCard
                key={ind.code}
                indicator={ind}
                subscribed={ind.subscribed ?? false}
                isSelected={selectedCode === ind.code}
                onSelect={() => setSelectedCode(selectedCode === ind.code ? null : ind.code)}
                onToggleSubscribe={() => handleToggleSubscribe(ind.code, ind.subscribed ?? false)}
                isPending={subscribe.isPending || unsubscribe.isPending}
              />
            ))}
          </div>
        )}
      </section>

      {/* 선택된 지표 추이 차트 */}
      {selectedIndicator && (
        <section
          aria-label={`${selectedIndicator.name} 추이`}
          className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-5"
        >
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-semibold text-gray-800 dark:text-gray-200">
                {selectedIndicator.name} — 24개월 추이
              </h2>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                {selectedIndicator.description}
              </p>
            </div>
          </div>
          {isHistoryLoading ? (
            <div className="h-48 flex items-center justify-center text-sm text-gray-400">
              차트 로딩 중...
            </div>
          ) : (
            <IndicatorHistoryChart
              data={history}
              name={selectedIndicator.name}
              unit={selectedIndicator.unit}
              isDark={isDark}
            />
          )}
        </section>
      )}
    </div>
  );
}
