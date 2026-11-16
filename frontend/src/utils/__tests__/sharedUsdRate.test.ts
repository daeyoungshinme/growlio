import { describe, it, expect } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { syncSharedUsdRate } from "@/utils/sharedUsdRate";

const read = (qc: QueryClient) =>
  qc.getQueryData<{ usd_krw: number; is_fallback?: boolean }>(QUERY_KEYS.exchangeRate);

describe("syncSharedUsdRate (plans/134)", () => {
  it("더 새로운 실환율이면 앱 전역 환율을 맞춘다", () => {
    const qc = new QueryClient();
    qc.setQueryData(
      QUERY_KEYS.exchangeRate,
      { usd_krw: 1370, is_fallback: false },
      { updatedAt: 1000 },
    );
    syncSharedUsdRate(qc, 1385.6, true, 2000);
    expect(read(qc)).toEqual({ usd_krw: 1385.6, is_fallback: false });
    expect(qc.getQueryState(QUERY_KEYS.exchangeRate)?.dataUpdatedAt).toBe(2000);
  });

  it("전역 환율이 없으면 채운다", () => {
    const qc = new QueryClient();
    syncSharedUsdRate(qc, 1385.6, true, 2000);
    expect(read(qc)?.usd_krw).toBe(1385.6);
  });

  it("전역 환율이 더 새로우면 덮지 않는다", () => {
    const qc = new QueryClient();
    qc.setQueryData(
      QUERY_KEYS.exchangeRate,
      { usd_krw: 1390, is_fallback: false },
      { updatedAt: 3000 },
    );
    syncSharedUsdRate(qc, 1385.6, true, 2000);
    expect(read(qc)?.usd_krw).toBe(1390);
  });

  it("실환율이 아니거나 값이 없으면 덮지 않는다", () => {
    const qc = new QueryClient();
    qc.setQueryData(
      QUERY_KEYS.exchangeRate,
      { usd_krw: 1370, is_fallback: false },
      { updatedAt: 1000 },
    );
    syncSharedUsdRate(qc, 1385.6, false, 2000);
    syncSharedUsdRate(qc, null, true, 2000);
    syncSharedUsdRate(qc, 0, true, 2000);
    expect(read(qc)?.usd_krw).toBe(1370);
  });
});
