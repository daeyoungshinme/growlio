import { describe, it, expect, vi } from "vitest";
import {
  invalidateSyncData,
  invalidateAccountData,
  invalidateTransactionData,
  invalidatePortfolioData,
  invalidateDcaData,
  invalidateAlertData,
  invalidateStockPriceAlertData,
  invalidateRebalancingAlertData,
} from "../queryInvalidation";

function makeQueryClient() {
  return {
    invalidateQueries: vi.fn().mockResolvedValue(undefined),
  };
}

describe("invalidateSyncData", () => {
  it("portfolio-overview, dashboard, dividend, insights 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateSyncData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("portfolio-overview");
    expect(keys).toContain("dashboard");
    expect(keys).toContain("dividend-by-ticker");
    expect(keys).toContain("insights");
  });
});

describe("invalidateAccountData", () => {
  it("accounts, portfolio-overview, dashboard 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateAccountData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("accounts");
    expect(keys).toContain("portfolio-overview");
    expect(keys).toContain("dashboard");
  });
});

describe("invalidateTransactionData", () => {
  it("transactions, dashboard 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateTransactionData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("transactions");
    expect(keys).toContain("dashboard");
  });
});

describe("invalidatePortfolioData", () => {
  it("portfolios, accounts 무효화", async () => {
    const qc = makeQueryClient();
    await invalidatePortfolioData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("portfolios");
    expect(keys).toContain("accounts");
  });
});

describe("invalidateDcaData", () => {
  it("dca-analysis, settings, dashboard 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateDcaData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("dca-analysis");
    expect(keys).toContain("settings");
    expect(keys).toContain("dashboard");
  });
});

describe("invalidateAlertData", () => {
  it("exchange-rate-alerts 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateAlertData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("exchange-rate-alerts");
  });
});

describe("invalidateStockPriceAlertData", () => {
  it("stock-price-alerts 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateStockPriceAlertData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("stock-price-alerts");
  });
});

describe("invalidateRebalancingAlertData", () => {
  it("rebalancing-alerts, rebalancing-alert(portfolioId) 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateRebalancingAlertData(qc as any, "portfolio-123");
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("rebalancing-alerts");
    expect(keys).toContain("rebalancing-alert");
    const alertCall = qc.invalidateQueries.mock.calls.find(
      (c) => c[0].queryKey[0] === "rebalancing-alert"
    );
    expect(alertCall![0].queryKey[1]).toBe("portfolio-123");
  });
});
