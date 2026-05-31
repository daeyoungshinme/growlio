import { useQuery } from "@tanstack/react-query";
import { fetchExchangeRate } from "../api/assets";
import { QUERY_KEYS } from "../constants/queryKeys";
import { STALE_TIME } from "../constants/queryConfig";

export function useExchangeRate() {
  const { data } = useQuery({
    queryKey: QUERY_KEYS.exchangeRate,
    queryFn: fetchExchangeRate,
    staleTime: STALE_TIME.EXCHANGE_RATE,
  });
  return data?.usd_krw ?? null;
}
