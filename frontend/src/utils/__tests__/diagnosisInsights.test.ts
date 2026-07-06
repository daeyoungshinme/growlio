import { describe, it, expect } from "vitest";
import { buildDiagnosisNotes, buildCombinedStatusNote } from "../diagnosisInsights";
import type { DiagnosisContext } from "../../api/rebalancing";

function makeContext(overrides: Partial<DiagnosisContext> = {}): DiagnosisContext {
  return {
    generated_at: "2026-07-03T00:00:00+00:00",
    market_level: "GREEN",
    market_note: null,
    risk_available: true,
    annualized_volatility_pct: 10,
    beta_sp500: 1.0,
    diversification_score: 80,
    risk_note: null,
    composite_signal_triggered: false,
    composite_signal_reason: null,
    estimated_sell_realized_gain_krw: 0,
    estimated_overseas_tax_krw: 0,
    estimated_fee_krw: 0,
    tax_notes: [],
    tax_detail_items: [],
    goal_annual_return_pct: null,
    goal_annual_dividend_krw: null,
    ...overrides,
  };
}

describe("buildDiagnosisNotes", () => {
  it("market_note가 없으면 시장 인사이트를 생략한다", () => {
    const notes = buildDiagnosisNotes(makeContext({ market_note: null }));
    expect(notes.some((n) => n.icon === "market")).toBe(false);
  });

  it("market_note가 있으면 포함한다", () => {
    const notes = buildDiagnosisNotes(
      makeContext({ market_note: "시장 변동성이 확대되는 국면입니다" }),
    );
    const note = notes.find((n) => n.icon === "market");
    expect(note).toBeDefined();
    expect(note?.text).toBe("시장 변동성이 확대되는 국면입니다");
  });

  it("risk_note가 없으면 리스크 인사이트를 생략한다", () => {
    const notes = buildDiagnosisNotes(makeContext({ risk_note: null }));
    expect(notes.some((n) => n.icon === "risk")).toBe(false);
  });

  it("risk_note가 있으면 포함한다", () => {
    const notes = buildDiagnosisNotes(makeContext({ risk_note: "분산도 점수가 낮습니다 (30점)" }));
    expect(notes.some((n) => n.icon === "risk")).toBe(true);
  });

  it("세금영향이 1만원 이하이면 생략한다", () => {
    const notes = buildDiagnosisNotes(
      makeContext({ estimated_overseas_tax_krw: 5_000, estimated_fee_krw: 3_000 }),
    );
    expect(notes.some((n) => n.icon === "tax")).toBe(false);
  });

  it("세금영향이 1만원을 초과하면 포함한다", () => {
    const notes = buildDiagnosisNotes(
      makeContext({ estimated_overseas_tax_krw: 100_000, estimated_fee_krw: 5_000 }),
    );
    const note = notes.find((n) => n.icon === "tax");
    expect(note).toBeDefined();
    expect(note?.text).toContain("참고용 추정치");
  });

  it("모든 신호가 정상이면 빈 배열을 반환한다", () => {
    const notes = buildDiagnosisNotes(makeContext());
    expect(notes).toEqual([]);
  });

  it("세 신호 모두 있으면 세 항목 모두 반환한다", () => {
    const notes = buildDiagnosisNotes(
      makeContext({
        market_note: "시장 위험 신호가 높은 국면입니다",
        risk_note: "특정 종목 비중이 45%로 과집중되어 있습니다",
        estimated_overseas_tax_krw: 200_000,
      }),
    );
    expect(notes).toHaveLength(3);
    expect(notes.map((n) => n.icon)).toEqual(["market", "risk", "tax"]);
  });

  it("목표 수익률이 미설정이면 목표 인사이트를 생략한다", () => {
    const notes = buildDiagnosisNotes(
      makeContext({ goal_annual_return_pct: null }),
      6.5,
      2_000_000,
    );
    expect(notes.some((n) => n.icon === "goal")).toBe(false);
  });

  it("목표 수익률이 설정되어 있으면 목표 대비 기대수익률 인사이트를 포함한다", () => {
    const notes = buildDiagnosisNotes(makeContext({ goal_annual_return_pct: 8 }), 6.5, null);
    const note = notes.find((n) => n.icon === "goal");
    expect(note).toBeDefined();
    expect(note?.text).toContain("목표 연 수익률 8.0%");
    expect(note?.text).toContain("6.5%");
    expect(note?.text).toContain("-1.5%p");
  });

  it("목표 배당이 설정되어 있으면 목표 대비 예상 배당 인사이트를 포함한다", () => {
    const notes = buildDiagnosisNotes(
      makeContext({ goal_annual_dividend_krw: 3_000_000 }),
      null,
      2_500_000,
    );
    const note = notes.find((n) => n.icon === "goal");
    expect(note).toBeDefined();
    expect(note?.text).toContain("목표 연간배당");
  });

  it("targetCagrPct가 없으면(analysis 계산 실패) 목표가 설정돼 있어도 생략한다", () => {
    const notes = buildDiagnosisNotes(makeContext({ goal_annual_return_pct: 8 }), null, null);
    expect(notes.some((n) => n.icon === "goal")).toBe(false);
  });
});

describe("buildCombinedStatusNote", () => {
  it("이탈 종목이 없으면 null을 반환한다", () => {
    expect(buildCombinedStatusNote(0, "RED")).toBeNull();
  });

  it("시장상황이 없으면 null을 반환한다", () => {
    expect(buildCombinedStatusNote(2, null)).toBeNull();
    expect(buildCombinedStatusNote(2, undefined)).toBeNull();
  });

  it("GREEN이면 null을 반환한다", () => {
    expect(buildCombinedStatusNote(2, "GREEN")).toBeNull();
  });

  it("YELLOW + 이탈 종목 있으면 분할 실행 문구를 반환한다", () => {
    const note = buildCombinedStatusNote(1, "YELLOW");
    expect(note).toContain("분할 실행");
  });

  it("RED + 이탈 종목 있으면 신중 검토 문구를 반환한다", () => {
    const note = buildCombinedStatusNote(1, "RED");
    expect(note).toContain("신중하게 검토");
  });
});
