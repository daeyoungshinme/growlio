import { apiGet } from "./client";

export interface DisclosureItem {
  rcept_no: string;
  corp_name: string;
  ticker: string;
  report_nm: string;
  rcept_dt: string;
  rm: string;
  dart_url: string;
}

export const fetchDartDisclosures = (days: number) =>
  apiGet<DisclosureItem[]>("/dart/disclosures", { params: { days } });
