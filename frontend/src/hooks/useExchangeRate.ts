import { useExchangeRateContext } from "@/context/ExchangeRateContext";

/** USD/KRW 환율(로딩·실패 시 null). 실패 토스트는 ExchangeRateProvider가 한 번만 띄운다. */
export function useExchangeRate() {
  return useExchangeRateContext().rate;
}
