import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { useStockAccountStats } from "@/hooks/useStockAccountStats";
import type { AssetAccount } from "@/api/assets";
import type { TransactionTotal } from "@/api/transactions";

describe("useStockAccountStats", () => {
  it("계좌 카드 입금·배당 누계는 서버 합계(txTotals)를 그대로 쓴다 (plans/90 B2)", () => {
    const accounts = [{ id: "a1" }, { id: "a2" }] as AssetAccount[];
    const totals: TransactionTotal[] = [
      { account_id: "a1", transaction_type: "DEPOSIT", total_amount: 12_000_000, count: 240 },
      { account_id: "a1", transaction_type: "DIVIDEND", total_amount: 35_000, count: 12 },
      { account_id: "a1", transaction_type: "WITHDRAWAL", total_amount: 500_000, count: 1 },
      { account_id: null, transaction_type: "DEPOSIT", total_amount: 999, count: 1 },
    ];
    const { result } = renderHook(() => useStockAccountStats(accounts, undefined, totals));
    expect(result.current[0]!.stats.deposit_total).toBe(12_000_000);
    expect(result.current[0]!.stats.dividend_total).toBe(35_000);
    expect(result.current[1]!.stats.deposit_total).toBe(0);
  });
});
