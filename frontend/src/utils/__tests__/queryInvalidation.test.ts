import { describe, it, expect, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { QUERY_KEYS } from "@/constants/queryKeys";
import {
  invalidateSyncData,
  invalidateAccountData,
  invalidateTransactionData,
  invalidatePortfolioData,
  invalidateDcaData,
  invalidateDividendPlanData,
  invalidateAlertData,
  invalidateStockPriceAlertData,
  invalidateRebalancingAlertData,
  invalidateRebalancingHistoryData,
  invalidateGoalRecommendationData,
  invalidateChallengeData,
  invalidateChallengeRemindersData,
  invalidateTradeData,
  invalidateRebalancingPlanData,
} from "../queryInvalidation";

function makeQueryClient() {
  return {
    invalidateQueries: vi.fn().mockResolvedValue(undefined),
  };
}

describe("invalidateSyncData", () => {
  it("accounts, portfolio-overview, dashboard, dividend, insights, drift-summary 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateSyncData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("accounts");
    expect(keys).toContain("portfolio-overview");
    expect(keys).toContain("dashboard");
    expect(keys).toContain("dividend-by-ticker");
    expect(keys).toContain("insights");
    expect(keys).toContain("drift-summary");
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
    // 연금·IRP 계좌 추가/삭제·tax_type 변경은 연금 납입 현황을 바꾼다
    expect(keys).toContain("pension-contribution");
  });
});

describe("invalidateTransactionData", () => {
  it("transactions, dashboard, challenges 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateTransactionData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("transactions");
    expect(keys).toContain("dashboard");
    expect(keys).toContain("challenges");
    // 백엔드 isa_service가 입금·배당 거래를 합산 — 절세 액션 플랜만 갱신되고 ISA 카드는 stale하던 버그
    expect(keys).toContain("isa-status");
    expect(keys).toContain("pension-contribution");
  });
});

describe("invalidateChallengeData", () => {
  it("challenges, dashboard 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateChallengeData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("challenges");
    expect(keys).toContain("dashboard");
  });
});

describe("invalidateChallengeRemindersData", () => {
  it("settings 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateChallengeRemindersData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("settings");
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

describe("invalidateDividendPlanData", () => {
  it("dividend-plan 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateDividendPlanData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("dividend-plan");
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
      (c) => c[0].queryKey[0] === "rebalancing-alert",
    );
    expect(alertCall![0].queryKey[1]).toBe("portfolio-123");
  });
});

describe("invalidateRebalancingHistoryData", () => {
  it("rebalancing-history 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateRebalancingHistoryData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("rebalancing-history");
  });
});

describe("invalidateGoalRecommendationData", () => {
  it("goal-recommendation(접두사 매칭), settings 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateGoalRecommendationData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("goal-recommendation");
    expect(keys).toContain("settings");
  });
});

describe("invalidateTradeData", () => {
  it("trades + period-purchases 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateTradeData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toEqual(["trades", "period-purchases"]);
  });

  it("계좌 sync·CUD도 기간별 매수(스냅샷 추정)를 갱신", async () => {
    for (const fn of [invalidateSyncData, invalidateAccountData]) {
      const qc = makeQueryClient();
      await fn(qc as any);
      const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
      expect(keys).toContain("period-purchases");
    }
  });
});

describe("invalidateRebalancingPlanData", () => {
  it("취소·실패는 대기 플랜·이력만 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateRebalancingPlanData(qc as any);
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("rebalancing-plans");
    expect(keys).toContain("rebalancing-history");
    expect(keys).not.toContain("drift-summary");
  });

  it("승인 즉시 체결(executed)이면 보유·드리프트·지금 할 일까지 무효화", async () => {
    const qc = makeQueryClient();
    await invalidateRebalancingPlanData(qc as any, { executed: true });
    const keys = qc.invalidateQueries.mock.calls.map((c) => c[0].queryKey[0]);
    expect(keys).toContain("drift-summary");
    expect(keys).toContain("action-items");
    expect(keys).toContain("dashboard");
  });
});

describe("실제 QueryClient 프리픽스 매칭", () => {
  function seeded() {
    const qc = new QueryClient();
    qc.setQueryData(QUERY_KEYS.transactions("acc-1"), []);
    qc.setQueryData(QUERY_KEYS.allTransactions(2026), []);
    qc.setQueryData(QUERY_KEYS.portfolioRisk("p-1"), {});
    return qc;
  }
  const invalidated = (qc: QueryClient, key: readonly unknown[]) =>
    qc.getQueryState(key)?.isInvalidated;

  it("거래 CUD 후 계좌별 거래내역 캐시도 무효화된다", async () => {
    const qc = seeded();
    await invalidateTransactionData(qc);
    expect(invalidated(qc, QUERY_KEYS.transactions("acc-1"))).toBe(true);
    expect(invalidated(qc, QUERY_KEYS.allTransactions(2026))).toBe(true);
  });

  it("계좌 CUD 후 계좌별 거래내역 캐시도 무효화된다", async () => {
    const qc = seeded();
    await invalidateAccountData(qc);
    expect(invalidated(qc, QUERY_KEYS.transactions("acc-1"))).toBe(true);
  });

  it("sync 후 포트폴리오별 리스크 캐시도 무효화된다", async () => {
    const qc = seeded();
    await invalidateSyncData(qc);
    expect(invalidated(qc, QUERY_KEYS.portfolioRisk("p-1"))).toBe(true);
  });
});
