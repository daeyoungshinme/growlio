import { useState } from "react";
import { useExchangeRate } from "@/hooks/useExchangeRate";
import { convertUsdToKrw } from "@/utils/format";

type AmountCurrency = "KRW" | "USD";

export const USD_CONVERSION_ERROR =
  "환율 정보를 불러오지 못해 달러 금액을 원화로 환산할 수 없습니다";

/**
 * 거래 금액의 달러 입력 상태 — 저장되는 값은 항상 원화(`setAmountKrw`)이고 달러는 입력 보조다.
 * 환율 없이 USD로 바꾸면 원화 금액을 비운다: 남겨 두면 빈 `$` 칸 뒤로 이전 원화 금액이 저장됐다(plans/95 F3·98 B).
 */
export function useUsdAmountInput(amountKrw: number, setAmountKrw: (krw: number) => void) {
  const usdRate = useExchangeRate();
  const [currency, setCurrency] = useState<AmountCurrency>("KRW");
  const [amountUsd, setAmountUsd] = useState(0);

  const switchCurrency = (c: AmountCurrency) => {
    if (c === currency) return;
    setCurrency(c);
    if (c === "KRW") {
      setAmountUsd(0);
      return;
    }
    const usd = usdRate && amountKrw ? parseFloat((amountKrw / usdRate).toFixed(2)) : 0;
    setAmountUsd(usd);
    setAmountKrw(convertUsdToKrw(usd, usdRate));
  };

  const changeUsd = (usd: number) => {
    setAmountUsd(usd);
    setAmountKrw(convertUsdToKrw(usd, usdRate));
  };

  const reset = () => {
    setCurrency("KRW");
    setAmountUsd(0);
  };

  /** 제출 전 가드 — USD 배당인데 환율이 없으면 원화 환산이 불가능하다. */
  const conversionError = (txType: string): string | null =>
    currency === "USD" && txType === "DIVIDEND" && !usdRate ? USD_CONVERSION_ERROR : null;

  return { currency, amountUsd, usdRate, switchCurrency, changeUsd, reset, conversionError };
}
