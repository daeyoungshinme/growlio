import { apiDelete, apiGet, apiPost } from "./client";

export interface IndicatorLatest {
  code: string;
  name: string;
  name_en: string;
  unit: string;
  frequency: string;
  description: string;
  latest_value: number;
  latest_date: string;
  previous_value: number | null;
  previous_date: string | null;
  change: number | null;
  change_pct: number | null;
  subscribed?: boolean;
}

export interface EconomicCalendarEvent {
  event: string;
  date: string;
  time_kst: string | null;
  country: string;
  actual: number | null;
  estimate: number | null;
  previous: number | null;
  impact: "High" | "Medium" | "Low" | null;
  currency: string | null;
}

export interface HistoryPoint {
  date: string;
  value: number;
}

export const fetchIndicators = () =>
  apiGet<IndicatorLatest[]>("/economic-indicators");

export const fetchIndicatorCalendar = () =>
  apiGet<EconomicCalendarEvent[]>("/economic-indicators/calendar");

export const fetchIndicatorHistory = (code: string, months = 24) =>
  apiGet<HistoryPoint[]>(`/economic-indicators/${code}/history`, { params: { months } });

export const fetchIndicatorSubscriptions = () =>
  apiGet<string[]>("/economic-indicators/subscriptions");

export const subscribeIndicator = (code: string) =>
  apiPost(`/economic-indicators/${code}/subscribe`);

export const unsubscribeIndicator = (code: string) =>
  apiDelete(`/economic-indicators/${code}/subscribe`);
