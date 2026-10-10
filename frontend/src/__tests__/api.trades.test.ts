import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/client", () => {
  const mockApi = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  };
  return {
    api: mockApi,
    apiGet: (url: string, ...args: unknown[]) =>
      mockApi.get(url, ...args).then((r: { data: unknown }) => r.data),
    apiPost: (url: string, ...args: unknown[]) =>
      mockApi.post(url, ...args).then((r: { data: unknown }) => r.data),
    apiPut: (url: string, ...args: unknown[]) =>
      mockApi.put(url, ...args).then((r: { data: unknown }) => r.data),
    apiPatch: (url: string, ...args: unknown[]) =>
      mockApi.patch(url, ...args).then((r: { data: unknown }) => r.data),
    apiDelete: (url: string, ...args: unknown[]) =>
      mockApi.delete(url, ...args).then((r: { data: unknown }) => r.data),
  };
});

import { api } from "@/api/client";
import {
  createTrade,
  deleteTrade,
  fetchPeriodPurchases,
  fetchTrades,
  updateTrade,
} from "@/api/trades";

describe("api/trades", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchPeriodPurchases → GET /trades/period-summary (기간 파라미터)", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { items: [] } });
    await fetchPeriodPurchases({ period: "month", year: 2026, month: 10, account_id: "acc-1" });
    expect(api.get).toHaveBeenCalledWith("/trades/period-summary", {
      params: { period: "month", year: 2026, month: 10, account_id: "acc-1" },
    });
  });

  it("fetchTrades → GET /trades (종목 필터)", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchTrades({ account_id: "acc-1", ticker: "005930", market: "KOSPI" });
    expect(api.get).toHaveBeenCalledWith("/trades", {
      params: { account_id: "acc-1", ticker: "005930", market: "KOSPI" },
    });
  });

  it("createTrade → POST /trades", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { id: "t-1" } });
    const body = {
      account_id: "acc-1",
      side: "BUY" as const,
      ticker: "005930",
      market: "KOSPI",
      qty: 1,
      price_krw: 70000,
      trade_date: "2026-10-02",
    };
    expect(await createTrade(body)).toEqual({ id: "t-1" });
    expect(api.post).toHaveBeenCalledWith("/trades", body);
  });

  it("updateTrade → PUT /trades/:id (null은 비우기로 그대로 전송)", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: { id: "t-1" } });
    await updateTrade("t-1", { qty: 2, fee: null, notes: null });
    expect(api.put).toHaveBeenCalledWith("/trades/t-1", { qty: 2, fee: null, notes: null });
  });

  it("deleteTrade → DELETE /trades/:id", async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: undefined });
    await deleteTrade("t-1");
    expect(api.delete).toHaveBeenCalledWith("/trades/t-1");
  });
});
