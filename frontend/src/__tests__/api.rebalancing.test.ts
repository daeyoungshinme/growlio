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
  analyzePortfolio,
  executeRebalancing,
  fetchBrokerBalance,
  fetchAllBrokerBalances,
  quickExecuteRebalancing,
  fetchRebalancingHistory,
  fetchRebalancingExecutionDetail,
  fetchDriftSummary,
} from "@/api/rebalancing";

describe("api/rebalancing", () => {
  beforeEach(() => vi.clearAllMocks());

  it("analyzePortfolio calls GET /rebalancing/portfolios/:id/analyze without accounts", async () => {
    const mockResult = { portfolio_id: "port-1", items: [] };
    vi.mocked(api.get).mockResolvedValue({ data: mockResult });
    const result = await analyzePortfolio("port-1");
    expect(api.get).toHaveBeenCalledWith("/rebalancing/portfolios/port-1/analyze", {
      params: undefined,
    });
    expect(result).toEqual(mockResult);
  });

  it("analyzePortfolio passes accountIds as URLSearchParams", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await analyzePortfolio("port-1", ["acc-1", "acc-2"]);
    const [url, config] = vi.mocked(api.get).mock.calls[0];
    expect(url).toBe("/rebalancing/portfolios/port-1/analyze");
    const params = config!.params as URLSearchParams;
    expect(params.getAll("account_ids")).toEqual(["acc-1", "acc-2"]);
  });

  it("executeRebalancing calls POST /rebalancing/portfolios/:id/execute", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: [] });
    await executeRebalancing("port-1", { orders: [] });
    expect(api.post).toHaveBeenCalledWith("/rebalancing/portfolios/port-1/execute", { orders: [] });
  });

  it("fetchBrokerBalance calls GET /rebalancing/broker-balance/:accountId", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await fetchBrokerBalance("acc-1");
    expect(api.get).toHaveBeenCalledWith("/rebalancing/broker-balance/acc-1");
  });

  it("fetchAllBrokerBalances calls GET /rebalancing/broker-balance-all", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchAllBrokerBalances();
    expect(api.get).toHaveBeenCalledWith("/rebalancing/broker-balance-all");
  });

  it("quickExecuteRebalancing calls POST /rebalancing/portfolios/:id/quick-execute", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: [] });
    await quickExecuteRebalancing("port-1");
    expect(api.post).toHaveBeenCalledWith("/rebalancing/portfolios/port-1/quick-execute");
  });

  it("fetchRebalancingHistory calls GET /rebalancing/history with default limit", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchRebalancingHistory();
    expect(api.get).toHaveBeenCalledWith("/rebalancing/history", { params: { limit: 20 } });
  });

  it("fetchRebalancingHistory calls GET /rebalancing/history with custom limit", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchRebalancingHistory(10);
    expect(api.get).toHaveBeenCalledWith("/rebalancing/history", { params: { limit: 10 } });
  });

  it("fetchRebalancingExecutionDetail calls GET /rebalancing/history/:id", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await fetchRebalancingExecutionDetail("exec-1");
    expect(api.get).toHaveBeenCalledWith("/rebalancing/history/exec-1");
  });

  it("fetchDriftSummary calls GET /rebalancing/drift-summary", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    const result = await fetchDriftSummary();
    expect(api.get).toHaveBeenCalledWith("/rebalancing/drift-summary");
    expect(result).toEqual([]);
  });
});
