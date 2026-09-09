import { describe, it, expect } from "vitest";
import type { PortfolioRiskMetrics } from "@/api/risk";
import { buildMetrics, summarizeRiskLevel, LEVEL_BADGE } from "@/utils/riskLevel";

function metrics(overrides: Partial<PortfolioRiskMetrics> = {}): PortfolioRiskMetrics {
  return {
    var_95_pct: 1,
    var_99_pct: 2,
    annualized_volatility_pct: 5,
    beta_sp500: 0.5,
    diversification_score: 80,
    top_holding_weight_pct: 10,
    position_count: 12,
    data_available: true,
    note: "",
    ...overrides,
  };
}

describe("buildMetrics", () => {
  it("6개 지표를 라벨·값·레벨·설명과 함께 반환한다", () => {
    const rows = buildMetrics(metrics());
    expect(rows).toHaveLength(6);
    expect(rows.map((r) => r.label)).toEqual([
      "VaR (95%)",
      "VaR (99%)",
      "연간 변동성",
      "S&P500 베타",
      "분산도 점수",
      "최대 종목 비중",
    ]);
    rows.forEach((r) => {
      expect(typeof r.value).toBe("string");
      expect(["low", "medium", "high"]).toContain(r.level);
      expect(r.description.length).toBeGreaterThan(0);
    });
  });

  it("안전한 값이면 전부 low, 위험한 값이면 전부 high로 분류한다", () => {
    const low = buildMetrics(metrics());
    expect(low.every((r) => r.level === "low")).toBe(true);

    const high = buildMetrics(
      metrics({
        var_95_pct: 6,
        var_99_pct: 10,
        annualized_volatility_pct: 25,
        beta_sp500: 1.5,
        diversification_score: 20,
        top_holding_weight_pct: 50,
      }),
    );
    expect(high.every((r) => r.level === "high")).toBe(true);
  });

  it("VaR·변동성·베타·집중도 임계값 경계에서 medium으로 전이한다", () => {
    const rows = buildMetrics(
      metrics({
        var_95_pct: 2, // <2 low → 2 medium
        var_99_pct: 3, // <3 low → 3 medium
        annualized_volatility_pct: 10, // <10 low → 10 medium
        beta_sp500: 0.8, // <0.8 low → 0.8 medium
        diversification_score: 40, // >=70 low, >=40 medium
        top_holding_weight_pct: 20, // <20 low → 20 medium
      }),
    );
    expect(rows.every((r) => r.level === "medium")).toBe(true);
  });
});

describe("summarizeRiskLevel", () => {
  it("data_available=false면 null을 반환한다", () => {
    expect(summarizeRiskLevel(metrics({ data_available: false }))).toBeNull();
  });

  it("high 지표가 없으면 safe", () => {
    expect(summarizeRiskLevel(metrics())).toEqual({ highCount: 0, level: "safe" });
  });

  it("high 지표 1~2개면 caution", () => {
    const res = summarizeRiskLevel(metrics({ annualized_volatility_pct: 25 }));
    expect(res).toEqual({ highCount: 1, level: "caution" });
  });

  it("high 지표 3개 이상이면 risk", () => {
    const res = summarizeRiskLevel(
      metrics({ var_95_pct: 6, annualized_volatility_pct: 25, top_holding_weight_pct: 50 }),
    );
    expect(res?.level).toBe("risk");
    expect(res?.highCount).toBeGreaterThanOrEqual(3);
  });
});

describe("LEVEL_BADGE", () => {
  it("low/medium/high 각각 라벨·클래스를 갖는다", () => {
    expect(LEVEL_BADGE.low.label).toBe("낮음");
    expect(LEVEL_BADGE.medium.label).toBe("보통");
    expect(LEVEL_BADGE.high.label).toBe("높음");
    (["low", "medium", "high"] as const).forEach((k) => {
      expect(LEVEL_BADGE[k].cls).toContain("dark:");
    });
  });
});
