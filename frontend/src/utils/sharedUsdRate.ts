import type { QueryClient } from "@tanstack/react-query";
import { QUERY_KEYS } from "@/constants/queryKeys";
import type { fetchExchangeRate } from "@/api/assets";

type ExchangeRateData = Awaited<ReturnType<typeof fetchExchangeRate>>;

/**
 * 환전 계획처럼 환율을 함께 받는 응답이 앱 전역 환율(`exchange-rate`, 홈·달러 환산 입력)보다 새로우면 그 값으로 맞춘다.
 * 서버는 같은 캐시를 읽지만 받은 시점이 달라 홈과 계획 카드 환율이 어긋났다(plans/134).
 * 실환율이 아니면(1년 종가 대체) 덮지 않는다 — 종가를 실환율처럼 퍼뜨리지 않게(plans/110 A7).
 */
export function syncSharedUsdRate(
  qc: QueryClient,
  rate: number | null | undefined,
  isLive: boolean,
  updatedAt: number,
): void {
  if (!isLive || !rate || rate <= 0 || !updatedAt) return;
  const current = qc.getQueryState<ExchangeRateData>(QUERY_KEYS.exchangeRate);
  if (current && current.dataUpdatedAt >= updatedAt) return;
  if (current?.data?.usd_krw === rate && current.data.is_fallback !== true) return;
  qc.setQueryData<ExchangeRateData>(
    QUERY_KEYS.exchangeRate,
    { usd_krw: rate, is_fallback: false },
    { updatedAt },
  );
}
