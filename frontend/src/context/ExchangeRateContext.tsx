import { createContext, useContext, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { exchangeRateQuery } from "@/api/queryOptions";
import { toast } from "@/utils/toast";

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
  const { data, isLoading, error } = useQuery(exchangeRateQuery);

  const rate = data?.usd_krw ?? null;

  // 실패 토스트는 여기서 한 번만 — 소비 훅마다 띄우면 마운트된 화면 수(최대 13곳)만큼 같은 토스트가 쌓였다(plans/95 G)
  useEffect(() => {
    if (error) {
      toast("환율 데이터를 불러오지 못했습니다. 해외 주식 금액이 부정확할 수 있습니다.", "error");
    }
  }, [error]);
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
