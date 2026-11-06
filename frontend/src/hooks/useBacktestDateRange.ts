import { useCallback, useState } from "react";
import { backtestDefaultEndDate, backtestDefaultStartDate } from "@/constants/defaults";

/** 오늘(로컬)로부터 `years`년 전 "YYYY-MM-DD" — 2월 29일이면 평년의 2월 28일로 맞춘다 */
export function yearsAgoLocal(years: number, today: Date = new Date()): string {
  const year = today.getFullYear() - years;
  const month = today.getMonth();
  const lastDay = new Date(year, month + 1, 0).getDate();
  const day = Math.min(today.getDate(), lastDay);
  return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function useBacktestDateRange() {
  const [startDate, setStartDateRaw] = useState(backtestDefaultStartDate);
  const [endDate, setEndDateRaw] = useState(backtestDefaultEndDate);
  const [activePreset, setActivePreset] = useState<number | null>(5);

  const setStartDate = useCallback((value: string) => {
    setStartDateRaw(value);
    setActivePreset(null);
  }, []);

  const setEndDate = useCallback((value: string) => {
    setEndDateRaw(value);
    setActivePreset(null);
  }, []);

  const setPreset = useCallback((years: number) => {
    const now = new Date();
    const start = years === 30 ? `${now.getFullYear() - 30}-01-01` : yearsAgoLocal(years, now);
    setStartDateRaw(start);
    setEndDateRaw(backtestDefaultEndDate());
    setActivePreset(years);
  }, []);

  return { startDate, endDate, activePreset, setStartDate, setEndDate, setPreset };
}
