import { Bell, BellOff, TrendingDown, TrendingUp, Minus } from "lucide-react";
import type { IndicatorLatest } from "@/api/economicIndicators";

interface Props {
  indicator: IndicatorLatest;
  subscribed: boolean;
  isSelected: boolean;
  onSelect: () => void;
  onToggleSubscribe: () => void;
  isPending?: boolean;
}

export default function IndicatorCard({
  indicator,
  subscribed,
  isSelected,
  onSelect,
  onToggleSubscribe,
  isPending = false,
}: Props) {
  const { name, unit, latest_value, previous_value, change_pct, latest_date } = indicator;

  const formattedValue = !Number.isFinite(latest_value)
    ? "—"
    : unit === "%"
      ? `${latest_value.toFixed(2)}%`
      : latest_value.toFixed(1);

  const formattedPrev =
    previous_value != null && Number.isFinite(previous_value)
      ? unit === "%"
        ? `${previous_value.toFixed(2)}%`
        : previous_value.toFixed(1)
      : null;

  const changeAbs = change_pct !== null ? Math.abs(change_pct) : null;
  const isUp = change_pct !== null && change_pct > 0;
  const isDown = change_pct !== null && change_pct < 0;

  const dateStr = latest_date ? latest_date.slice(0, 7) : "";

  return (
    <button
      onClick={onSelect}
      className={`w-full text-left rounded-2xl border p-3 sm:p-4 transition-all focus:outline-none focus:ring-2 focus:ring-blue-400 ${
        isSelected
          ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30 shadow-sm"
          : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600"
      }`}
      aria-label={`${name} 상세 보기`}
      aria-pressed={isSelected}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="min-w-0">
          <p className="text-xs text-gray-400 dark:text-gray-500">{dateStr}</p>
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 mt-0.5 leading-tight line-clamp-2">
            {name}
          </p>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleSubscribe();
          }}
          disabled={isPending}
          aria-label={subscribed ? "구독 해제" : "구독"}
          title={subscribed ? "알림 구독 해제" : "발표 시 알림 받기"}
          className={`shrink-0 p-2.5 rounded-xl transition-colors ${
            subscribed
              ? "text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30"
              : "text-gray-400 dark:text-gray-500 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/30"
          } disabled:opacity-50`}
        >
          {subscribed ? <Bell size={16} /> : <BellOff size={16} />}
        </button>
      </div>

      <p className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-50 tabular-nums">{formattedValue}</p>

      <div className="mt-2 space-y-1">
        <div className="flex items-center gap-1.5">
          {isUp && (
            <>
              <TrendingUp size={14} className="text-red-500 shrink-0" />
              <span className="text-xs font-medium text-red-500">+{changeAbs?.toFixed(2)}%</span>
            </>
          )}
          {isDown && (
            <>
              <TrendingDown size={14} className="text-blue-500 shrink-0" />
              <span className="text-xs font-medium text-blue-500">-{changeAbs?.toFixed(2)}%</span>
            </>
          )}
          {!isUp && !isDown && change_pct !== null && (
            <>
              <Minus size={14} className="text-gray-400 shrink-0" />
              <span className="text-xs text-gray-400">변동 없음</span>
            </>
          )}
        </div>
        {formattedPrev && (
          <p className="text-xs text-gray-400 dark:text-gray-500">
            전월 {formattedPrev}
          </p>
        )}
      </div>
    </button>
  );
}
