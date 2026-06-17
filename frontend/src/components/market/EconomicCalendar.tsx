import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Calendar } from "lucide-react";
import type { EconomicCalendarEvent } from "@/api/economicIndicators";

interface Props {
  events: EconomicCalendarEvent[];
}

const DAYS_OF_WEEK = ["일", "월", "화", "수", "목", "금", "토"];

const COUNTRY_FLAG: Record<string, string> = {
  US: "🇺🇸",
  EU: "🇪🇺",
  GB: "🇬🇧",
  JP: "🇯🇵",
  CN: "🇨🇳",
  CA: "🇨🇦",
  AU: "🇦🇺",
};

const IMPACT_DOT: Record<string, string> = {
  High: "bg-red-500",
  Medium: "bg-yellow-400",
  Low: "bg-gray-400",
};

const IMPACT_BADGE_CLS: Record<string, string> = {
  High: "bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400",
  Medium: "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-600 dark:text-yellow-400",
  Low: "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400",
};

const IMPACT_LABEL: Record<string, string> = {
  High: "고",
  Medium: "중",
  Low: "저",
};

function getTodayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function formatSelectedDateHeader(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
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
  return base;
}

function formatValue(val: number | null | undefined, currency: string | null | undefined): string {
  if (val == null || !Number.isFinite(val)) return "—";
  const suffix = currency ? ` ${currency}` : "";
  return `${val}${suffix}`;
}

function getTopImpact(events: EconomicCalendarEvent[]): string | null {
  if (events.some((e) => e.impact === "High")) return "High";
  if (events.some((e) => e.impact === "Medium")) return "Medium";
  if (events.some((e) => e.impact === "Low")) return "Low";
  if (events.length > 0) return "Low";
  return null;
}

export default function EconomicCalendar({ events }: Props) {
  const todayStr = getTodayStr();
  const today = new Date();

  const [currentMonth, setCurrentMonth] = useState(
    () => new Date(today.getFullYear(), today.getMonth(), 1),
  );
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const minMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  const maxMonth = new Date(today.getFullYear(), today.getMonth() + 2, 1);
  const canPrev = currentMonth > minMonth;
  const canNext = currentMonth < maxMonth;

  const eventsByDate = useMemo(() => {
    const map = new Map<string, EconomicCalendarEvent[]>();
    for (const e of events) {
      const key = e.date?.split("T")[0];
      if (!key) continue;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(e);
    }
    return map;
  }, [events]);

  const calendarCells = useMemo(() => {
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth();
    const firstDow = new Date(year, month, 1).getDay();
    const lastDay = new Date(year, month + 1, 0).getDate();
    return [
      ...Array<null>(firstDow).fill(null),
      ...Array.from({ length: lastDay }, (_, i) => {
        const d = i + 1;
        return `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      }),
    ];
  }, [currentMonth]);

  const monthKeyEvents = useMemo(() => {
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth();
    const prefix = `${year}-${String(month + 1).padStart(2, "0")}`;
    const highs = events
      .filter((e) => e.date?.startsWith(prefix) && e.impact === "High")
      .map((e) => e.event);
    return [...new Set(highs)];
  }, [events, currentMonth]);

  const selectedEvents = selectedDate ? (eventsByDate.get(selectedDate) ?? []) : [];

  const handlePrev = () => {
    if (!canPrev) return;
    setCurrentMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1));
    setSelectedDate(null);
  };

  const handleNext = () => {
    if (!canNext) return;
    setCurrentMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1));
    setSelectedDate(null);
  };

  const handleSelectDate = (dateStr: string) => {
    setSelectedDate((prev) => (prev === dateStr ? null : dateStr));
  };

  const year = currentMonth.getFullYear();
  const month = currentMonth.getMonth();

  return (
    <div className="space-y-3">
      {/* 월 네비게이션 */}
      <div className="flex items-center justify-between">
        <button
          onClick={handlePrev}
          disabled={!canPrev}
          aria-label="이전 달"
          className="p-2 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronLeft size={18} />
        </button>
        <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
          {year}년 {month + 1}월
        </span>
        <button
          onClick={handleNext}
          disabled={!canNext}
          aria-label="다음 달"
          className="p-2 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronRight size={18} />
        </button>
      </div>

      {/* 이번달 주요 발표 */}
      {monthKeyEvents.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          <span className="text-xs text-gray-400 dark:text-gray-500 self-center">주요 발표</span>
          {monthKeyEvents.map((name) => (
            <span
              key={name}
              className="text-xs px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400"
            >
              {name}
            </span>
          ))}
        </div>
      )}

      {/* 요일 헤더 */}
      <div className="grid grid-cols-7 text-center">
        {DAYS_OF_WEEK.map((d, i) => (
          <div
            key={d}
            className={`text-xs font-medium py-1 ${
              i === 0 || i === 6
                ? "text-red-400 dark:text-red-400"
                : "text-gray-400 dark:text-gray-500"
            }`}
          >
            {d}
          </div>
        ))}
      </div>

      {/* 날짜 그리드 */}
      <div className="grid grid-cols-7 gap-px">
        {calendarCells.map((dateStr, i) => {
          if (!dateStr) {
            return <div key={`empty-${i}`} className="aspect-square" />;
          }

          const dayEvents = eventsByDate.get(dateStr) ?? [];
          const hasEvents = dayEvents.length > 0;
          const isToday = dateStr === todayStr;
          const isSelected = dateStr === selectedDate;
          const isPast = dateStr < todayStr;
          const topImpact = getTopImpact(dayEvents);
          const dayNum = new Date(dateStr + "T00:00:00").getDate();
          const dow = new Date(dateStr + "T00:00:00").getDay();
          const isWeekend = dow === 0 || dow === 6;

          return (
            <button
              key={dateStr}
              onClick={() => handleSelectDate(dateStr)}
              aria-label={`${month + 1}월 ${dayNum}일${hasEvents ? ` — 이벤트 ${dayEvents.length}건` : ""}`}
              aria-pressed={isSelected}
              className={`flex flex-col items-center justify-start py-1 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400 ${
                isSelected && !isToday
                  ? "bg-blue-50 dark:bg-blue-900/20"
                  : "hover:bg-gray-50 dark:hover:bg-gray-700/50"
              } ${isPast ? "opacity-40" : ""}`}
            >
              <span
                className={`text-xs w-7 h-7 flex items-center justify-center rounded-full font-medium ${
                  isToday
                    ? "bg-blue-600 text-white"
                    : isSelected
                      ? "text-blue-600 dark:text-blue-400"
                      : isWeekend
                        ? "text-red-400 dark:text-red-400"
                        : "text-gray-700 dark:text-gray-200"
                }`}
              >
                {dayNum}
              </span>
              <span className="h-1.5 mt-0.5 flex items-center justify-center">
                {topImpact && (
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${IMPACT_DOT[topImpact]}`}
                    aria-hidden="true"
                  />
                )}
              </span>
            </button>
          );
        })}
      </div>

      {/* 선택된 날짜 이벤트 상세 */}
      {selectedDate && (
        <div className="mt-1 pt-3 border-t border-gray-100 dark:border-gray-700">
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
            {formatSelectedDateHeader(selectedDate)}
          </p>
          {selectedEvents.length === 0 ? (
            <p className="text-sm text-gray-400 dark:text-gray-500 py-2">예정된 발표가 없습니다.</p>
          ) : (
            <div className="space-y-2">
              {selectedEvents.map((event, i) => {
                const flag = COUNTRY_FLAG[event.country] ?? "";
                const hasResult = Number.isFinite(event.actual as number);
                const showValue = hasResult || Number.isFinite(event.estimate as number);
                const impactCls = event.impact
                  ? IMPACT_BADGE_CLS[event.impact]
                  : IMPACT_BADGE_CLS.Low;

                return (
                  <div
                    key={`${event.event}-${i}`}
                    className="flex items-start gap-3 p-3 rounded-xl bg-gray-50 dark:bg-gray-800/60"
                  >
                    <div className="shrink-0 flex items-center justify-center w-8 h-8 rounded-lg bg-white dark:bg-gray-700 shadow-sm text-lg">
                      {flag || <Calendar size={16} className="text-gray-400" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-800 dark:text-gray-100 leading-snug">
                        {event.event}
                      </p>
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        {event.time_kst && (
                          <span className="text-xs text-gray-400 dark:text-gray-500">
                            {event.time_kst} KST
                          </span>
                        )}
                        {showValue && (
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            {hasResult ? "실제" : "예측"}{" "}
                            <span className="font-semibold text-gray-700 dark:text-gray-200">
                              {formatValue(
                                hasResult ? event.actual : event.estimate,
                                event.currency,
                              )}
                            </span>
                          </span>
                        )}
                        {event.impact && (
                          <span
                            className={`text-xs font-medium px-2 py-0.5 rounded-full ${impactCls}`}
                          >
                            {IMPACT_LABEL[event.impact] ?? event.impact}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* 범례 */}
      <div className="flex items-center gap-3 pt-1">
        {(["High", "Medium", "Low"] as const).map((level) => (
          <div key={level} className="flex items-center gap-1">
            <span className={`w-2 h-2 rounded-full ${IMPACT_DOT[level]}`} aria-hidden="true" />
            <span className="text-xs text-gray-400 dark:text-gray-500">{IMPACT_LABEL[level]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
