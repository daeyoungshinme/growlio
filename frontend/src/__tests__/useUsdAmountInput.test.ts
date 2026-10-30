import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useUsdAmountInput, USD_CONVERSION_ERROR } from "@/hooks/useUsdAmountInput";

const exchangeRate = vi.hoisted(() => ({ value: 1350 as number | null }));
vi.mock("@/hooks/useExchangeRate", () => ({
  useExchangeRate: () => exchangeRate.value,
}));

describe("useUsdAmountInput", () => {
  beforeEach(() => {
    exchangeRate.value = 1350;
  });

  it("환율이 있으면 USD 전환 시 원화 금액을 달러로 환산해 유지한다", () => {
    const setKrw = vi.fn();
    const { result } = renderHook(() => useUsdAmountInput(1350000, setKrw));
    act(() => result.current.switchCurrency("USD"));
    expect(result.current.currency).toBe("USD");
    expect(result.current.amountUsd).toBe(1000);
    expect(setKrw).toHaveBeenCalledWith(1350000);
  });

  // 남겨 두면 빈 $ 칸 뒤로 이전 원화 금액이 저장됐다(plans/98 B)
  it("환율 없이 USD로 전환하면 원화 금액을 비우고 제출 가드가 오류를 낸다", () => {
    exchangeRate.value = null;
    const setKrw = vi.fn();
    const { result } = renderHook(() => useUsdAmountInput(50000, setKrw));
    act(() => result.current.switchCurrency("USD"));
    expect(result.current.amountUsd).toBe(0);
    expect(setKrw).toHaveBeenCalledWith(0);
    expect(result.current.conversionError("DIVIDEND")).toBe(USD_CONVERSION_ERROR);
  });

  it("KRW로 돌아오면 원화 금액은 두고 달러 입력만 비운다", () => {
    const setKrw = vi.fn();
    const { result } = renderHook(() => useUsdAmountInput(0, setKrw));
    act(() => result.current.switchCurrency("USD"));
    act(() => result.current.changeUsd(10));
    expect(setKrw).toHaveBeenLastCalledWith(13500);
    setKrw.mockClear();
    act(() => result.current.switchCurrency("KRW"));
    expect(result.current.amountUsd).toBe(0);
    expect(setKrw).not.toHaveBeenCalled();
    expect(result.current.conversionError("DIVIDEND")).toBeNull();
  });
});
