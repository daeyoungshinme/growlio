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
  fetchDashboard,
  fetchDividendByTicker,
  updateTickerDividendMonths,
  deleteTickerDividendMonths,
} from "@/api/dashboard";

describe("api/dashboard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchDashboard calls GET /dashboard", async () => {
    const mockData = { total_assets_krw: 10000000 };
    vi.mocked(api.get).mockResolvedValue({ data: mockData });
    const result = await fetchDashboard();
    expect(api.get).toHaveBeenCalledWith("/dashboard");
    expect(result).toEqual(mockData);
  });

  it("fetchDividendByTicker calls GET /dividends/by-ticker", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    const result = await fetchDividendByTicker();
    expect(api.get).toHaveBeenCalledWith("/dividends/by-ticker");
    expect(result).toEqual([]);
  });

  it("updateTickerDividendMonths calls PUT /dividends/ticker-settings/:ticker", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: {} });
    await updateTickerDividendMonths("005930", "KOSPI", [3, 6, 9, 12]);
    expect(api.put).toHaveBeenCalledWith("/dividends/ticker-settings/005930", {
      market: "KOSPI",
      dividend_months: [3, 6, 9, 12],
    });
  });

  it("deleteTickerDividendMonths calls DELETE /dividends/ticker-settings/:ticker", async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: {} });
    await deleteTickerDividendMonths("005930", "KOSPI");
    expect(api.delete).toHaveBeenCalledWith("/dividends/ticker-settings/005930", {
      params: { market: "KOSPI" },
    });
  });
});
