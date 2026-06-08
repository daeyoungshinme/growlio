import { createContext, useContext } from "react";
import { useExchangeRate } from "../hooks/useExchangeRate";

const ExchangeRateContext = createContext<number | null>(null);

export function ExchangeRateProvider({ children }: { children: React.ReactNode }) {
  const usdRate = useExchangeRate();
  return (
    <ExchangeRateContext.Provider value={usdRate}>
      {children}
    </ExchangeRateContext.Provider>
  );
}

export function useExchangeRateContext(): number | null {
  return useContext(ExchangeRateContext);
}
