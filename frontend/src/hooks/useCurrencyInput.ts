import { useState } from "react";
import { convertUsdToKrw } from "@/utils/format";
import { useExchangeRate } from "./useExchangeRate";

export function useCurrencyInput(initialKrw?: number, initialUsd?: number) {
  const [depositKrw, setDepositKrw] = useState<number | undefined>(initialKrw);
  const [depositUsd, setDepositUsd] = useState<number | undefined>(initialUsd);
  const usdRate = useExchangeRate();

  const usdAsKrw = convertUsdToKrw(depositUsd, usdRate);
  const totalKrw = (depositKrw ?? 0) + usdAsKrw;
  const hasAnyDeposit = (depositKrw ?? 0) > 0 || (depositUsd ?? 0) > 0;
  const usdPending = (depositUsd ?? 0) > 0 && usdRate == null;

  return {
    depositKrw,
    depositUsd,
    usdRate,
    usdAsKrw,
    totalKrw,
    hasAnyDeposit,
    usdPending,
    setDepositKrw,
    setDepositUsd,
  };
}
