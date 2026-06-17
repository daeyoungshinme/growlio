import { useState } from "react";
import { useExchangeRate } from "./useExchangeRate";

export function useCurrencyInput(initialKrw?: number, initialUsd?: number) {
  const [depositKrw, setDepositKrw] = useState<number | undefined>(initialKrw);
  const [depositUsd, setDepositUsd] = useState<number | undefined>(initialUsd);
  const usdRate = useExchangeRate();

  const usdAsKrw = depositUsd != null && usdRate != null ? Math.round(depositUsd * usdRate) : 0;
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
