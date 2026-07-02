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
  fetchExchangeRateAlerts,
  createExchangeRateAlert,
  reactivateExchangeRateAlert,
  deleteExchangeRateAlert,
  fetchRebalancingAlerts,
  fetchRebalancingAlert,
  upsertRebalancingAlert,
  deleteRebalancingAlert,
  fetchStockPriceAlerts,
  createStockPriceAlert,
  reactivateStockPriceAlert,
  deleteStockPriceAlert,
  fetchAlertHistory,
} from "@/api/alerts";

const mockExchangeAlert = {
  id: "alert-1",
  target_rate: 1300,
  direction: "BELOW" as const,
  is_active: true,
  max_trigger_count: 1,
  trigger_count: 0,
  triggered_at: null,
  created_at: "2024-01-01T00:00:00Z",
};

describe("api/alerts — exchange rate alerts", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchExchangeRateAlerts calls GET /alerts/exchange-rate", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [mockExchangeAlert] });
    const result = await fetchExchangeRateAlerts();
    expect(api.get).toHaveBeenCalledWith("/alerts/exchange-rate");
    expect(result).toEqual([mockExchangeAlert]);
  });

  it("createExchangeRateAlert calls POST /alerts/exchange-rate", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: mockExchangeAlert });
    const result = await createExchangeRateAlert(1300, "BELOW", 1);
    expect(api.post).toHaveBeenCalledWith("/alerts/exchange-rate", {
      target_rate: 1300,
      direction: "BELOW",
      max_trigger_count: 1,
    });
    expect(result).toEqual(mockExchangeAlert);
  });

  it("createExchangeRateAlert uses default max_trigger_count=1", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: mockExchangeAlert });
    await createExchangeRateAlert(1300, "BELOW");
    expect(api.post).toHaveBeenCalledWith(
      "/alerts/exchange-rate",
      expect.objectContaining({
        max_trigger_count: 1,
      }),
    );
  });

  it("reactivateExchangeRateAlert calls PATCH /alerts/exchange-rate/:id/reactivate", async () => {
    vi.mocked(api.patch).mockResolvedValue({ data: mockExchangeAlert });
    await reactivateExchangeRateAlert("alert-1");
    expect(api.patch).toHaveBeenCalledWith("/alerts/exchange-rate/alert-1/reactivate");
  });

  it("deleteExchangeRateAlert calls DELETE /alerts/exchange-rate/:id", async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: {} });
    await deleteExchangeRateAlert("alert-1");
    expect(api.delete).toHaveBeenCalledWith("/alerts/exchange-rate/alert-1");
  });
});

describe("api/alerts — rebalancing alerts", () => {
  beforeEach(() => vi.clearAllMocks());

  const mockRebalancingAlert = {
    id: "alert-2",
    portfolio_id: "port-1",
    is_active: true,
    threshold_pct: 5,
    schedule_type: "DAILY" as const,
    schedule_day_of_week: null,
    schedule_day_of_month: null,
    only_when_drift: true,
    trigger_condition: "DRIFT_ONLY" as const,
    mode: "NOTIFY" as const,
    strategy: "FULL" as const,
    account_id: null,
    order_type: "MARKET" as const,
    market_condition_mode: "DISABLED" as const,
    auto_execution_time: null,
    notify_time: "08:30",
    last_triggered_at: null,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
  };

  it("fetchRebalancingAlerts calls GET /alerts/rebalancing", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [mockRebalancingAlert] });
    const result = await fetchRebalancingAlerts();
    expect(api.get).toHaveBeenCalledWith("/alerts/rebalancing");
    expect(result).toEqual([mockRebalancingAlert]);
  });

  it("fetchRebalancingAlert calls GET /alerts/rebalancing/:portfolioId", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: mockRebalancingAlert });
    await fetchRebalancingAlert("port-1");
    expect(api.get).toHaveBeenCalledWith("/alerts/rebalancing/port-1");
  });

  it("upsertRebalancingAlert calls PUT /alerts/rebalancing/:portfolioId", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: mockRebalancingAlert });
    await upsertRebalancingAlert("port-1", {
      threshold_pct: 5,
      schedule_type: "DAILY",
      schedule_day_of_week: null,
      schedule_day_of_month: null,
      trigger_condition: "DRIFT_ONLY" as const,
      mode: "NOTIFY",
      strategy: "FULL",
      account_id: null,
      order_type: "MARKET",
      market_condition_mode: "DISABLED",
      auto_execution_time: null,
      notify_time: "08:30",
    });
    expect(api.put).toHaveBeenCalledWith(
      "/alerts/rebalancing/port-1",
      expect.objectContaining({
        portfolio_id: "port-1",
      }),
    );
  });

  it("deleteRebalancingAlert calls DELETE /alerts/rebalancing/:portfolioId", async () => {
    vi.mocked(api.delete).mockResolvedValue({});
    await deleteRebalancingAlert("port-1");
    expect(api.delete).toHaveBeenCalledWith("/alerts/rebalancing/port-1");
  });
});

describe("api/alerts — stock price alerts", () => {
  beforeEach(() => vi.clearAllMocks());

  const mockStockAlert = {
    id: "alert-3",
    ticker: "005930",
    market: "KOSPI",
    name: "삼성전자",
    target_price: 80000,
    direction: "ABOVE" as const,
    is_active: true,
    max_trigger_count: 1,
    trigger_count: 0,
    triggered_at: null,
    created_at: "2024-01-01T00:00:00Z",
  };

  it("fetchStockPriceAlerts calls GET /alerts/stock-price", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [mockStockAlert] });
    const result = await fetchStockPriceAlerts();
    expect(api.get).toHaveBeenCalledWith("/alerts/stock-price");
    expect(result).toEqual([mockStockAlert]);
  });

  it("createStockPriceAlert calls POST /alerts/stock-price", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: mockStockAlert });
    const body = {
      ticker: "005930",
      market: "KOSPI",
      name: "삼성전자",
      target_price: 80000,
      direction: "ABOVE" as const,
    };
    await createStockPriceAlert(body);
    expect(api.post).toHaveBeenCalledWith("/alerts/stock-price", body);
  });

  it("reactivateStockPriceAlert calls PATCH", async () => {
    vi.mocked(api.patch).mockResolvedValue({ data: mockStockAlert });
    await reactivateStockPriceAlert("alert-3");
    expect(api.patch).toHaveBeenCalledWith("/alerts/stock-price/alert-3/reactivate");
  });

  it("deleteStockPriceAlert calls DELETE", async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: {} });
    await deleteStockPriceAlert("alert-3");
    expect(api.delete).toHaveBeenCalledWith("/alerts/stock-price/alert-3");
  });
});

describe("api/alerts — alert history", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchAlertHistory calls GET /alerts/history without params", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchAlertHistory();
    expect(api.get).toHaveBeenCalledWith("/alerts/history", { params: undefined });
  });

  it("fetchAlertHistory calls GET /alerts/history with params", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchAlertHistory({ skip: 0, limit: 20 });
    expect(api.get).toHaveBeenCalledWith("/alerts/history", { params: { skip: 0, limit: 20 } });
  });
});
