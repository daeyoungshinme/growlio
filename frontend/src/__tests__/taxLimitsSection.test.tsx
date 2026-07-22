import { describe, it, expect, vi, afterEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { IsaStatusSummary } from "@/api/tax";
import type { PortfolioOverview } from "@/types";

const fetchIsaStatus = vi.fn();
const fetchPensionContribution = vi.fn();
const fetchPortfolioOverviewLite = vi.fn();

vi.mock("@/api/tax", () => ({
  fetchIsaStatus: (...args: unknown[]) => fetchIsaStatus(...args),
  fetchPensionContribution: (...args: unknown[]) => fetchPensionContribution(...args),
}));

vi.mock("@/api/portfolios", () => ({
  fetchPortfolioOverviewLite: (...args: unknown[]) => fetchPortfolioOverviewLite(...args),
}));

import TaxLimitsSection from "@/components/portfolio-analysis/TaxLimitsSection";

function makeOverview(
  accounts: Array<{ investment_horizon?: string | null; tax_type?: string | null }>,
): PortfolioOverview {
  return {
    accounts: accounts.map((a, i) => ({
      id: `acc${i}`,
      name: `계좌${i}`,
      asset_type: "STOCK_KIS",
      amount_krw: 1_000_000,
      ...a,
    })),
  } as unknown as PortfolioOverview;
}

const emptyIsa: IsaStatusSummary = { accounts: [], note: "" };

describe("TaxLimitsSection", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("ISA/연금 계좌가 하나도 없으면 렌더링하지 않는다", async () => {
    fetchIsaStatus.mockResolvedValue(emptyIsa);
    fetchPortfolioOverviewLite.mockResolvedValue(makeOverview([{ tax_type: "GENERAL" }]));
    const { container } = renderWithProviders(<TaxLimitsSection />);
    await waitFor(() => expect(fetchIsaStatus).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("ISA 계좌가 있으면 카드를 렌더링하고, 토글 클릭 시 IsaMaturityCard가 펼쳐진다 (기본 접힘)", async () => {
    fetchIsaStatus.mockResolvedValue({
      accounts: [
        {
          account_id: "acc1",
          account_name: "일반형 ISA",
          isa_type: "GENERAL",
          isa_open_date: "2023-01-01",
          maturity_date: "2026-01-01",
          is_mature: true,
          days_remaining: 0,
          needs_open_date: false,
          estimated_cumulative_pnl_krw: 1_000_000,
          is_manual_override: false,
          tax_free_limit_krw: 2_000_000,
          taxable_excess_krw: 0,
          estimated_tax_krw: 0,
        },
      ],
      note: "추정치입니다.",
    } as IsaStatusSummary);
    fetchPortfolioOverviewLite.mockResolvedValue(makeOverview([]));

    renderWithProviders(<TaxLimitsSection />);
    expect(await screen.findByText("한도·기한 현황")).toBeInTheDocument();
    expect(screen.queryByText("ISA 만기·세제 현황")).toBeNull();

    fireEvent.click(screen.getByText("한도·기한 현황"));
    expect(await screen.findByText("ISA 만기·세제 현황")).toBeInTheDocument();
  });

  it("연금저축 태그 계좌가 있으면 토글 펼침 후 PensionContributionCard를 임베드 렌더한다", async () => {
    fetchIsaStatus.mockResolvedValue(emptyIsa);
    fetchPensionContribution.mockResolvedValue({
      year: 2026,
      pension_savings_deposit_krw: 3_000_000,
      irp_deposit_krw: 0,
      total_deposit_krw: 3_000_000,
      pension_savings_limit_krw: 6_000_000,
      total_limit_krw: 9_000_000,
      pension_savings_achievement_pct: 50.0,
      total_achievement_pct: 33.3,
      pension_savings_remaining_krw: 3_000_000,
      total_remaining_krw: 6_000_000,
      note: "수기 입력 기준입니다.",
    });
    fetchPortfolioOverviewLite.mockResolvedValue(makeOverview([{ tax_type: "PENSION_SAVINGS" }]));

    renderWithProviders(<TaxLimitsSection />);
    await screen.findByText("한도·기한 현황");
    fireEvent.click(screen.getByText("한도·기한 현황"));
    expect(await screen.findByText(/연금저축·IRP 납입 현황/)).toBeInTheDocument();
  });
});
