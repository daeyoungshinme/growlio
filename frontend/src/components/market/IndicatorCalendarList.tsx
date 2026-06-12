import { Calendar } from "lucide-react";
import type { EconomicCalendarEvent } from "@/api/economicIndicators";

interface Props {
  events: EconomicCalendarEvent[];
}

const COUNTRY_FLAG: Record<string, string> = {
  US: "🇺🇸",
  EU: "🇪🇺",
  GB: "🇬🇧",
  JP: "🇯🇵",
};

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "날짜 미상";
  const datePart = dateStr.split("T")[0];
  const d = new Date(datePart + "T00:00:00");
  if (isNaN(d.getTime())) return dateStr;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  d.setHours(0, 0, 0, 0);
  const diffDays = Math.round((d.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
  const month = d.getMonth() + 1;
  const day = d.getDate();
  const dayLabels = ["일", "월", "화", "수", "목", "금", "토"];
  const base = `${month}월 ${day}일(${dayLabels[d.getDay()]})`;
  if (diffDays === 0) return `오늘 · ${base}`;
  if (diffDays === 1) return `내일 · ${base}`;
  if (diffDays <= 7) return `${diffDays}일 후 · ${base}`;
  return base;
}

export default function IndicatorCalendarList({ events }: Props) {
  if (events.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400 dark:text-gray-500 text-sm">
        향후 14일 내 예정된 발표 일정이 없습니다.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {events.map((event, i) => {
        const flag = COUNTRY_FLAG[event.country] ?? "";

        return (
          <div
            key={`${event.event}-${i}`}
            className="flex items-center gap-3 p-3 rounded-xl bg-gray-50 dark:bg-gray-800/60 border border-transparent hover:border-gray-200 dark:hover:border-gray-700 transition-colors"
          >
            <div className="shrink-0 flex items-center justify-center w-8 h-8 rounded-lg bg-white dark:bg-gray-700 shadow-sm text-lg">
              {flag || <Calendar size={16} className="text-gray-400" />}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
                {event.event}
              </p>
              <p className="text-xs mt-0.5 text-gray-400 dark:text-gray-500">
                {formatDate(event.date)}
                {event.time_kst && ` · ${event.time_kst} KST`}
              </p>
            </div>
            {event.estimate != null && Number.isFinite(event.estimate) && (
              <div className="shrink-0 text-right">
                <p className="text-xs text-gray-400 dark:text-gray-500">예측</p>
                <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                  {event.estimate}
                </p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
