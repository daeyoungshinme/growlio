import { describe, it, expect } from "vitest";
import type { PortfolioRiskMetrics } from "@/api/risk";
import {
  buildMetrics,
  LEVEL_BADGE,
  riskHeadline,
  summarizeRiskLevel,
  topConcentration,
} from "@/utils/riskLevel";

function metrics(overrides: Partial<PortfolioRiskMetrics> = {}): PortfolioRiskMetrics {
  return {
    data_available: true,
    total_value_krw: 10_000_000,
    cash_weight_pct: 10,
    coverage_pct: 100,
    var_95_pct: 1,
    var_95_krw: 100_000,
    annualized_volatility_pct: 10,
    max_drawdown_pct: 5,
    beta_sp500: 0.6,
    vol_ratio_vs_sp500: 0.6,
    sp500_10pct_drop_krw: 540_000,
    top_holding_weight_pct: 20,
    top_holding_name: "삼성전자",
    top_index_exposures: [{ key: "SP500", label: "S&P500", pct_of_stock: 30 }],
    position_count: 8,
    note: null,
    ...overrides,
  };
}

describe("buildMetrics", () => {
  it("손실액·낙폭·시장 대비·쏠림 4행을 만든다", () => {
    const rows = buildMetrics(metrics());
    expect(rows.map((r) => r.key)).toEqual(["var", "mdd", "market", "concentration"]);
    expect(rows[0]?.value).toBe("-10만원");
    expect(rows[1]?.value).toBe("-5.0%");
    expect(rows[2]?.value).toBe("0.60배");
    expect(rows[3]?.value).toBe("S&P500 30%");
    rows.forEach((r) => expect(r.description.length).toBeGreaterThan(0));
  });

  it("안전한 값은 low, 위험한 값은 high", () => {
    expect(buildMetrics(metrics()).every((r) => r.level === "low")).toBe(true);
    const high = buildMetrics(
      metrics({
        var_95_pct: 3,
        max_drawdown_pct: 25,
        vol_ratio_vs_sp500: 1.5,
        top_index_exposures: [{ key: "NDX", label: "나스닥100", pct_of_stock: 70 }],
      }),
    );
    expect(high.every((r) => r.level === "high")).toBe(true);
  });

  it("시장 대비 1.0배 안팎은 보통(시장 수준)", () => {
    const row = buildMetrics(metrics({ vol_ratio_vs_sp500: 1.2 })).find((r) => r.key === "market");
    expect(row?.level).toBe("medium");
  });

  it("S&P500 비교가 없으면 그 행을 뺀다", () => {
    const rows = buildMetrics(metrics({ vol_ratio_vs_sp500: null }));
    expect(rows.some((r) => r.key === "market")).toBe(false);
  });

  it("10% 하락 시 영향액과 베타를 설명에 담는다", () => {
    const row = buildMetrics(metrics()).find((r) => r.key === "market");
    expect(row?.description).toContain("54만원");
    expect(row?.description).toContain("0.60");
  });
});

describe("topConcentration", () => {
  it("지수 노출이 단일 종목보다 크면 지수", () => {
    expect(topConcentration(metrics())).toEqual({ name: "S&P500", pct: 30 });
  });

  it("단일 종목이 더 크면 종목", () => {
    expect(topConcentration(metrics({ top_holding_weight_pct: 45 }))).toEqual({
      name: "삼성전자",
      pct: 45,
    });
  });

  it("둘 다 없으면 null", () => {
    expect(
      topConcentration(
        metrics({ top_index_exposures: [], top_holding_name: null, top_holding_weight_pct: 0 }),
      ),
    ).toBeNull();
  });
});

describe("summarizeRiskLevel / riskHeadline", () => {
  it("데이터가 없으면 null", () => {
    expect(summarizeRiskLevel(metrics({ data_available: false }))).toBeNull();
    expect(riskHeadline(metrics({ data_available: false }))).toBeNull();
  });

  it("high 개수로 safe/caution/risk", () => {
    expect(summarizeRiskLevel(metrics())?.level).toBe("safe");
    expect(summarizeRiskLevel(metrics({ max_drawdown_pct: 25 }))?.level).toBe("caution");
    expect(summarizeRiskLevel(metrics({ max_drawdown_pct: 25, var_95_pct: 3 }))?.level).toBe(
      "risk",
    );
  });

  it("헤드라인은 손실액과 쏠림 한 줄", () => {
    expect(riskHeadline(metrics())).toBe("나쁜 날 -10만원 · S&P500 30%");
  });

  it("LEVEL_BADGE 라벨", () => {
    expect(LEVEL_BADGE.high.label).toBe("높음");
  });
});
