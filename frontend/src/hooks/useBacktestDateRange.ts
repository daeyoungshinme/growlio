import { useCallback, useState } from "react";
import { BACKTEST_DEFAULT_END_DATE, BACKTEST_DEFAULT_START_DATE } from "@/constants/defaults";

export function useBacktestDateRange() {
  const [startDate, setStartDateRaw] = useState(BACKTEST_DEFAULT_START_DATE);
  const [endDate, setEndDateRaw] = useState(BACKTEST_DEFAULT_END_DATE);
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
    const end = BACKTEST_DEFAULT_END_DATE;
    const start =
      years === 30
        ? `${now.getFullYear() - 30}-01-01`
        : `${now.getFullYear() - years}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    setStartDateRaw(start);
    setEndDateRaw(end);
    setActivePreset(years);
  }, []);

  return { startDate, endDate, activePreset, setStartDate, setEndDate, setPreset };
}
