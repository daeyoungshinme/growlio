import { localToday } from "@/utils/format";

export const BACKTEST_DEFAULT_END_DATE = localToday();
export const BACKTEST_DEFAULT_START_DATE = `${new Date().getFullYear() - 5}-01-01`;
