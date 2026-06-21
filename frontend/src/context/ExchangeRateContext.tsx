import { createContext, useContext } from "react";
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

  return (
    <ExchangeRateContext.Provider
      value={{ rate: data?.usd_krw ?? null, isLoading, error: error as Error | null }}
    >
      {children}
    </ExchangeRateContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useExchangeRateContext(): ExchangeRateContextValue {
  return useContext(ExchangeRateContext);
}
