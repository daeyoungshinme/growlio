import { useEffect } from "react";
import { useExchangeRateContext } from "@/context/ExchangeRateContext";
import { toast } from "@/utils/toast";

export function useExchangeRate() {
  const { rate, error } = useExchangeRateContext();

  useEffect(() => {
    if (error) {
      toast("환율 데이터를 불러오지 못했습니다. 해외 주식 금액이 부정확할 수 있습니다.", "error");
    }
  }, [error]);

  return rate;
}
