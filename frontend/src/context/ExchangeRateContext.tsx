import { createContext, useContext, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchExchangeRate } from "@/api/assets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

export interface ExchangeRateContextValue {
  rate: number | null;
  isLoading: boolean;
  error: Error | null;
}

const ExchangeRateContext = createContext<ExchangeRateContextValue>({
  rate: null,
  isLoading: false,
  error: null,
});

export function ExchangeRateProvider({ children }: { children: React.ReactNode }) {
  const { data, isLoading, error } = useQuery({
    queryKey: QUERY_KEYS.exchangeRate,
    queryFn: fetchExchangeRate,
    staleTime: STALE_TIME.EXCHANGE_RATE,
  });

  const rate = data?.usd_krw ?? null;
  // 매 렌더 새 객체를 넘기면 AppLayout이 리렌더될 때마다(당겨서 새로고침 제스처 중 매 프레임 등) 환율을 쓰는
  // 컴포넌트 전부가 다시 렌더됐다
  const value = useMemo(
    () => ({ rate, isLoading, error: error as Error | null }),
    [rate, isLoading, error],
  );

  return <ExchangeRateContext.Provider value={value}>{children}</ExchangeRateContext.Provider>;
}

// 컴포넌트에서 직접 사용하지 말 것 — hooks/useExchangeRate.ts를 통해 소비할 것
// eslint-disable-next-line react-refresh/only-export-components
export function useExchangeRateContext(): ExchangeRateContextValue {
  return useContext(ExchangeRateContext);
}
