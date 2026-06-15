import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useTransactionFormState } from "@/hooks/useTransactionFormState";
import { ExchangeRateProvider } from "@/context/ExchangeRateContext";

vi.mock("@/api/assets", () => ({
  fetchExchangeRate: vi.fn().mockResolvedValue({ usd_krw: 1350 }),
  searchStocks: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <ExchangeRateProvider>{children}</ExchangeRateProvider>
    </QueryClientProvider>
  );
}

describe("useTransactionFormState", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("초기 상태가 올바르다", () => {
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    expect(result.current.form.account_id).toBe("acc-1");
    expect(result.current.form.transaction_type).toBe("DEPOSIT");
    expect(result.current.form.amount).toBe(0);
    expect(result.current.currency).toBe("KRW");
    expect(result.current.tickerDirect).toBe(false);
    expect(result.current.editingTx).toBeNull();
    expect(result.current.depositPrompt).toBeNull();
  });

  it("resetForm이 초기 상태로 되돌린다", () => {
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    act(() => {
      result.current.set("amount", 1000000);
      result.current.setFormError("에러");
    });
    act(() => {
      result.current.resetForm();
    });
    expect(result.current.form.amount).toBe(0);
    expect(result.current.formError).toBeNull();
    expect(result.current.currency).toBe("KRW");
  });

  it("startEdit이 편집 트랜잭션을 설정한다", () => {
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    const tx = {
      id: "tx-1",
      account_id: "acc-1",
      transaction_type: "DIVIDEND" as const,
      amount: 50000,
      fee: null,
      transaction_date: "2024-01-15",
      ticker: "005930",
      notes: "배당금",
      created_at: "2024-01-15T00:00:00Z",
    };
    act(() => {
      result.current.startEdit(tx);
    });
    expect(result.current.editingTx).toEqual(tx);
    expect(result.current.form.transaction_type).toBe("DIVIDEND");
    expect(result.current.form.amount).toBe(50000);
    expect(result.current.form.ticker).toBe("005930");
    expect(result.current.tickerDirect).toBe(true);
    expect(result.current.tickerQuery).toBe("005930");
  });

  it("startEdit이 ticker 없는 트랜잭션을 처리한다", () => {
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    const tx = {
      id: "tx-2",
      account_id: "acc-1",
      transaction_type: "DEPOSIT" as const,
      amount: 1000000,
      fee: null,
      transaction_date: "2024-01-10",
      ticker: null,
      notes: null,
      created_at: "2024-01-10T00:00:00Z",
    };
    act(() => {
      result.current.startEdit(tx);
    });
    expect(result.current.tickerDirect).toBe(false);
    expect(result.current.tickerQuery).toBe("");
  });

  it("triggerDepositPrompt가 양수 금액과 유효한 txType에서 작동한다", () => {
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    act(() => {
      result.current.triggerDepositPrompt(1000000, "DEPOSIT");
    });
    expect(result.current.depositPrompt).toEqual({ amount: 1000000, txType: "DEPOSIT" });
  });

  it("triggerDepositPrompt는 음수 금액을 무시한다", () => {
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    act(() => {
      result.current.triggerDepositPrompt(-1000, "DEPOSIT");
    });
    expect(result.current.depositPrompt).toBeNull();
  });

  it("triggerDepositPrompt는 유효하지 않은 txType을 무시한다", () => {
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    act(() => {
      result.current.triggerDepositPrompt(1000000, "INVALID");
    });
    expect(result.current.depositPrompt).toBeNull();
  });

  it("handleCurrencySwitch가 KRW에서 USD로 전환한다", async () => {
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.usdRate).toBe(1350));

    // set amount first, then switch currency in a separate act
    act(() => { result.current.set("amount", 1350000); });
    await waitFor(() => expect(result.current.form.amount).toBe(1350000));

    act(() => { result.current.handleCurrencySwitch("USD"); });
    expect(result.current.currency).toBe("USD");
    expect(result.current.amountUsd).toBeCloseTo(1000, 1);
  });

  it("handleCurrencySwitch가 동일 통화는 무시한다", () => {
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    const prevAmountUsd = result.current.amountUsd;
    act(() => {
      result.current.handleCurrencySwitch("KRW");
    });
    expect(result.current.currency).toBe("KRW");
    expect(result.current.amountUsd).toBe(prevAmountUsd);
  });

  it("handleCurrencySwitch가 USD에서 KRW로 전환 시 amountUsd를 0으로 리셋한다", async () => {
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.usdRate).toBe(1350));
    act(() => { result.current.handleCurrencySwitch("USD"); });
    act(() => { result.current.handleCurrencySwitch("KRW"); });
    expect(result.current.currency).toBe("KRW");
    expect(result.current.amountUsd).toBe(0);
  });

  it("handleUsdAmountChange가 USD 금액과 KRW 환산을 업데이트한다", async () => {
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.usdRate).toBe(1350));

    act(() => {
      result.current.handleUsdAmountChange(100);
    });
    expect(result.current.amountUsd).toBe(100);
    expect(result.current.form.amount).toBe(135000);
  });

  it("handleTxTypeChange가 transaction_type을 업데이트하고 관련 상태를 리셋한다", () => {
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    act(() => {
      result.current.handleCurrencySwitch("USD");
      result.current.setTickerDirect(true);
    });
    act(() => {
      result.current.handleTxTypeChange("WITHDRAWAL");
    });
    expect(result.current.form.transaction_type).toBe("WITHDRAWAL");
    expect(result.current.currency).toBe("KRW");
    expect(result.current.tickerDirect).toBe(false);
  });

  it("handleTickerQueryChange가 쿼리를 업데이트하고 검색을 실행한다", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    act(() => {
      result.current.handleTickerQueryChange("삼성");
    });
    expect(result.current.tickerQuery).toBe("삼성");
    expect(result.current.form.ticker).toBe("삼성");
    expect(result.current.showTickerSuggestions).toBe(true);
    vi.useRealTimers();
  });

  it("handleTickerQueryChange 빈 쿼리는 제안을 지운다", () => {
    const { result } = renderHook(() => useTransactionFormState("acc-1"), {
      wrapper: createWrapper(),
    });
    act(() => {
      result.current.handleTickerQueryChange("");
    });
    expect(result.current.tickerQuery).toBe("");
    expect(result.current.showTickerSuggestions).toBe(true);
  });
});
