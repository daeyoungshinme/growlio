import { api } from "./client";

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
  api.get<IndicatorLatest[]>("/economic-indicators").then((r) => r.data);

export const fetchIndicatorCalendar = () =>
  api.get<EconomicCalendarEvent[]>("/economic-indicators/calendar").then((r) => r.data);

export const fetchIndicatorHistory = (code: string, months = 24) =>
  api
    .get<HistoryPoint[]>(`/economic-indicators/${code}/history`, { params: { months } })
    .then((r) => r.data);

export const fetchIndicatorSubscriptions = () =>
  api.get<string[]>("/economic-indicators/subscriptions").then((r) => r.data);

export const subscribeIndicator = (code: string) =>
  api.post(`/economic-indicators/${code}/subscribe`);

export const unsubscribeIndicator = (code: string) =>
  api.delete(`/economic-indicators/${code}/subscribe`);
