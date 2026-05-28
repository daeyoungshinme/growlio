import { useQuery } from "@tanstack/react-query";
import { fetchExchangeRate } from "../api/assets";
import { QUERY_KEYS } from "../constants/queryKeys";

export function useExchangeRate() {
  const { data } = useQuery({
    queryKey: QUERY_KEYS.exchangeRate,
    queryFn: fetchExchangeRate,
    staleTime: 5 * 60 * 1000,
  });
  return data?.usd_krw ?? null;
}
