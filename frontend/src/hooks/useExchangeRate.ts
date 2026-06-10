import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchExchangeRate } from "@/api/assets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { toast } from "@/utils/toast";

export function useExchangeRate() {
  const { data, isError } = useQuery({
    queryKey: QUERY_KEYS.exchangeRate,
    queryFn: fetchExchangeRate,
    staleTime: STALE_TIME.EXCHANGE_RATE,
  });

  useEffect(() => {
    if (isError) {
      toast(
        "환율 데이터를 불러오지 못했습니다. 해외 주식 금액이 부정확할 수 있습니다.",
        "error"
      );
    }
  }, [isError]);

  return data?.usd_krw ?? null;
}
