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
  fetchAccounts,
  createAccount,
  updateAccount,
  deleteAccount,
  syncAccount,
  setAccountTargetPortfolio,
  batchSetTargetPortfolio,
  verifyKisCredentials,
  fetchSnapshots,
  searchStocks,
  fetchExchangeRate,
  fetchStockPrice,
} from "@/api/assets";

const mockAccount = {
  id: "acc-1",
  name: "테스트",
  asset_type: "STOCK_KIS",
  data_source: "KIS_API",
};

describe("api/assets", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetchAccounts calls GET /assets", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [mockAccount] });
    const result = await fetchAccounts();
    expect(api.get).toHaveBeenCalledWith("/assets");
    expect(result).toEqual([mockAccount]);
  });

  it("createAccount calls POST /assets", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: mockAccount });
    const result = await createAccount({ name: "테스트", asset_type: "STOCK_KIS" });
    expect(api.post).toHaveBeenCalledWith("/assets", { name: "테스트", asset_type: "STOCK_KIS" });
    expect(result).toEqual(mockAccount);
  });

  it("updateAccount calls PUT /assets/:id", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: mockAccount });
    const result = await updateAccount("acc-1", { name: "업데이트" });
    expect(api.put).toHaveBeenCalledWith("/assets/acc-1", { name: "업데이트" });
    expect(result).toEqual(mockAccount);
  });

  it("deleteAccount calls DELETE /assets/:id", async () => {
    vi.mocked(api.delete).mockResolvedValue({});
    await deleteAccount("acc-1");
    expect(api.delete).toHaveBeenCalledWith("/assets/acc-1");
  });

  it("syncAccount calls POST /assets/:id/sync", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: {} });
    await syncAccount("acc-1");
    expect(api.post).toHaveBeenCalledWith("/assets/acc-1/sync");
  });

  it("setAccountTargetPortfolio calls PATCH", async () => {
    vi.mocked(api.patch).mockResolvedValue({ data: mockAccount });
    const result = await setAccountTargetPortfolio("acc-1", "port-1");
    expect(api.patch).toHaveBeenCalledWith("/assets/acc-1/target-portfolio", {
      target_portfolio_id: "port-1",
    });
    expect(result).toEqual(mockAccount);
  });

  it("setAccountTargetPortfolio accepts null portfolioId", async () => {
    vi.mocked(api.patch).mockResolvedValue({ data: mockAccount });
    await setAccountTargetPortfolio("acc-1", null);
    expect(api.patch).toHaveBeenCalledWith("/assets/acc-1/target-portfolio", {
      target_portfolio_id: null,
    });
  });

  it("batchSetTargetPortfolio calls PATCH /assets/batch-target-portfolio", async () => {
    vi.mocked(api.patch).mockResolvedValue({ data: [mockAccount] });
    const result = await batchSetTargetPortfolio("port-1", ["acc-1", "acc-2"]);
    expect(api.patch).toHaveBeenCalledWith("/assets/batch-target-portfolio", {
      portfolio_id: "port-1",
      account_ids: ["acc-1", "acc-2"],
    });
    expect(result).toEqual([mockAccount]);
  });

  it("verifyKisCredentials calls POST /assets/verify-kis-credentials", async () => {
    const mockResponse = { valid: true, message: "OK" };
    vi.mocked(api.post).mockResolvedValue({ data: mockResponse });
    const result = await verifyKisCredentials({
      kis_app_key: "key",
      kis_app_secret: "secret",
      is_mock: false,
    });
    expect(api.post).toHaveBeenCalledWith("/assets/verify-kis-credentials", {
      kis_app_key: "key",
      kis_app_secret: "secret",
      is_mock: false,
    });
    expect(result).toEqual(mockResponse);
  });

  it("fetchSnapshots calls GET /assets/snapshots/range", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchSnapshots("2024-01-01", "2024-12-31");
    expect(api.get).toHaveBeenCalledWith("/assets/snapshots/range", {
      params: { start_date: "2024-01-01", end_date: "2024-12-31" },
    });
  });

  it("searchStocks calls GET /stocks/search with query", async () => {
    const mockSuggestions = [
      { ticker: "005930", name: "삼성전자", market: "KOSPI", exchange: "KRX" },
    ];
    vi.mocked(api.get).mockResolvedValue({ data: mockSuggestions });
    const result = await searchStocks("삼성");
    expect(api.get).toHaveBeenCalledWith("/stocks/search", {
      params: { q: "삼성" },
      signal: undefined,
    });
    expect(result).toEqual(mockSuggestions);
  });

  it("searchStocks passes abort signal", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    const controller = new AbortController();
    await searchStocks("test", controller.signal);
    expect(api.get).toHaveBeenCalledWith("/stocks/search", {
      params: { q: "test" },
      signal: controller.signal,
    });
  });

  it("fetchExchangeRate calls GET /stocks/exchange-rate", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { usd_krw: 1350 } });
    const result = await fetchExchangeRate();
    expect(api.get).toHaveBeenCalledWith("/stocks/exchange-rate");
    expect(result).toEqual({ usd_krw: 1350 });
  });

  it("fetchStockPrice calls GET /stocks/price", async () => {
    const mockPrice = { price_krw: 75000, price_usd: null, usd_rate: null };
    vi.mocked(api.get).mockResolvedValue({ data: mockPrice });
    const result = await fetchStockPrice("005930", "KOSPI");
    expect(api.get).toHaveBeenCalledWith("/stocks/price", {
      params: { ticker: "005930", market: "KOSPI" },
    });
    expect(result).toEqual(mockPrice);
  });
});
