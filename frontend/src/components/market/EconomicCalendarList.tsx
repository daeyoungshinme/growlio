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
  CN: "🇨🇳",
  CA: "🇨🇦",
  AU: "🇦🇺",
};

const IMPACT_STYLE: Record<string, { badge: string; dot: string }> = {
  High: {
    badge: "bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400",
    dot: "bg-red-500",
  },
  Medium: {
    badge: "bg-yellow-100 dark:bg-yellow-900/40 text-yellow-600 dark:text-yellow-400",
    dot: "bg-yellow-500",
  },
  Low: {
    badge: "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400",
    dot: "bg-gray-400",
  },
};

const IMPACT_LABEL: Record<string, string> = {
  High: "고",
  Medium: "중",
  Low: "저",
};

function groupByDate(events: EconomicCalendarEvent[]): Map<string, EconomicCalendarEvent[]> {
  const map = new Map<string, EconomicCalendarEvent[]>();
  for (const e of events) {
    if (!e.date) continue;
    const key = e.date.split("T")[0];
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(e);
  }
  return map;
}

function formatDateHeader(dateStr: string | null | undefined): string {
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
  const weekday = dayLabels[d.getDay()];
  const base = `${month}월 ${day}일(${weekday})`;

  if (diffDays === 0) return `오늘 · ${base}`;
  if (diffDays === 1) return `내일 · ${base}`;
  if (diffDays <= 7) return `${diffDays}일 후 · ${base}`;
  return base;
}

function formatValue(val: number | null | undefined, currency: string | null | undefined): string {
  if (val == null || !Number.isFinite(val)) return "—";
  const suffix = currency ? ` ${currency}` : "";
  return `${val}${suffix}`;
}

export default function EconomicCalendarList({ events }: Props) {
  if (events.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400 dark:text-gray-500 text-sm">
        향후 90일 내 예정된 이벤트가 없습니다.
        <br />
        <span className="text-xs">FRED API 키 설정을 확인하세요.</span>
      </div>
    );
  }

  const grouped = groupByDate(events);

  return (
    <div className="space-y-4">
      {Array.from(grouped.entries()).map(([dateStr, dayEvents]) => (
        <div key={dateStr}>
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 px-1">
            {formatDateHeader(dateStr)}
          </p>
          <div className="space-y-1.5">
            {dayEvents.map((event, i) => {
              const impactStyle = event.impact ? IMPACT_STYLE[event.impact] : IMPACT_STYLE.Low;
              const flag = COUNTRY_FLAG[event.country] ?? "";
              const hasResult = Number.isFinite(event.actual as number);
              const showValue = hasResult || Number.isFinite(event.estimate as number);

              return (
                <div
                  key={`${event.event}-${i}`}
                  className="flex items-center gap-3 p-3 rounded-xl bg-gray-50 dark:bg-gray-800/60 border border-transparent hover:border-gray-200 dark:hover:border-gray-700 transition-colors"
                >
                  {/* 국가 플래그 */}
                  <div className="shrink-0 flex items-center justify-center w-8 h-8 rounded-lg bg-white dark:bg-gray-700 shadow-sm text-lg">
                    {flag || <Calendar size={16} className="text-gray-400" />}
                  </div>

                  {/* 이벤트명 + 시간 */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
                      {event.event}
                    </p>
                    {event.time_kst && (
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                        {event.time_kst} KST
                      </p>
                    )}
                  </div>

                  {/* 예측/실제값 */}
                  {showValue && (
                    <div className="shrink-0 text-right">
                      {hasResult ? (
                        <>
                          <p className="text-xs text-gray-400 dark:text-gray-500">실제</p>
                          <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                            {formatValue(event.actual, event.currency)}
                          </p>
                        </>
                      ) : (
                        <>
                          <p className="text-xs text-gray-400 dark:text-gray-500">예측</p>
                          <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                            {formatValue(event.estimate, event.currency)}
                          </p>
                        </>
                      )}
                    </div>
                  )}

                  {/* impact 배지 */}
                  {event.impact && (
                    <span
                      className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${impactStyle.badge}`}
                    >
                      {IMPACT_LABEL[event.impact] ?? event.impact}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
