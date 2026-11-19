import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { MarketOutlook } from "@/api/marketSignals";
import type { PortfolioRiskMetrics } from "@/api/risk";
import type { PortfolioDriftSummary } from "@/api/rebalancing";
import DiagnosisSummaryStrip from "@/components/rebalancing/DiagnosisSummaryStrip";
import { buildDiagnosisChips } from "@/utils/diagnosisSummary";
import { DIAGNOSIS_ANCHORS } from "@/constants/rebalancingConfig";

const drift = (needs: boolean) =>
  ({ portfolio_id: "p", portfolio_name: "p", needs_rebalancing: needs }) as PortfolioDriftSummary;

const outlook = { verdict: "STEADY", label: "신중" } as MarketOutlook;

const risk = {
  data_available: true,
  top_holding_weight_pct: 20,
  top_holding_name: "A",
  top_index_exposures: [{ key: "NDX", label: "나스닥100", pct_of_stock: 65 }],
} as unknown as PortfolioRiskMetrics;

describe("buildDiagnosisChips", () => {
  it("이탈·시장·쏠림 칩", () => {
    const chips = buildDiagnosisChips({
      driftSummaries: [drift(true), drift(false)],
      outlook,
      risk,
    });
    expect(chips.map((c) => c.label)).toEqual([
      "이탈 포트폴리오 1개",
      "시장 신중",
      "쏠림 나스닥100 65%",
    ]);
  });

  it("데이터 없는 칩은 뺀다", () => {
    expect(buildDiagnosisChips({})).toEqual([]);
    expect(
      buildDiagnosisChips({
        driftSummaries: [drift(false)],
        outlook: { ...outlook, verdict: "UNKNOWN" },
      }).map((c) => c.label),
    ).toEqual(["이탈 없음"]);
  });
});

describe("DiagnosisSummaryStrip", () => {
  it("칩을 누르면 해당 카드로 스크롤한다", () => {
    const target = document.createElement("div");
    target.id = DIAGNOSIS_ANCHORS.risk;
    target.scrollIntoView = vi.fn();
    document.body.appendChild(target);

    render(<DiagnosisSummaryStrip risk={risk} />);
    fireEvent.click(screen.getByText("쏠림 나스닥100 65%"));
    expect(target.scrollIntoView).toHaveBeenCalled();
    target.remove();
  });

  it("칩이 없으면 아무것도 그리지 않는다", () => {
    const { container } = render(<DiagnosisSummaryStrip />);
    expect(container.firstChild).toBeNull();
  });
});
