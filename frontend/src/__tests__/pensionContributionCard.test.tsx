import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { PensionContributionStatus } from "@/api/tax";
import type { PortfolioOverview } from "@/types";

const fetchPensionContribution = vi.fn();

vi.mock("@/api/tax", () => ({
  fetchPensionContribution: (...args: unknown[]) => fetchPensionContribution(...args),
}));

import PensionContributionCard from "@/components/dashboard/PensionContributionCard";

function makeOverview(taxTypes: string[]): PortfolioOverview {
  return {
    accounts: taxTypes.map((tax_type, i) => ({
      id: `acc${i}`,
      name: `계좌${i}`,
      asset_type: "STOCK_KIS",
      amount_krw: 1_000_000,
      tax_type,
    })),
  } as unknown as PortfolioOverview;
}

function makeStatus(overrides: Partial<PensionContributionStatus> = {}): PensionContributionStatus {
  return {
    year: 2026,
    pension_savings_deposit_krw: 3_000_000,
    irp_deposit_krw: 1_000_000,
    total_deposit_krw: 4_000_000,
    pension_savings_limit_krw: 6_000_000,
    total_limit_krw: 9_000_000,
    pension_savings_achievement_pct: 50.0,
    total_achievement_pct: 44.4,
    pension_savings_remaining_krw: 3_000_000,
    total_remaining_krw: 5_000_000,
    note: "수기 입력 기준입니다.",
    ...overrides,
  };
}

describe("PensionContributionCard", () => {
  it("연금저축/IRP 계좌가 없으면 렌더링하지 않는다", async () => {
    const { container } = renderWithProviders(
      <PensionContributionCard overview={makeOverview(["GENERAL"])} />,
    );
    expect(fetchPensionContribution).not.toHaveBeenCalled();
    expect(container).toBeEmptyDOMElement();
  });

  it("연금저축 계좌가 있으면 진행률을 표시한다", async () => {
    fetchPensionContribution.mockResolvedValue(makeStatus());
    renderWithProviders(<PensionContributionCard overview={makeOverview(["PENSION_SAVINGS"])} />);
    await waitFor(() => expect(screen.getByText("50.0%")).toBeInTheDocument());
    expect(screen.getByText("44.4%")).toBeInTheDocument();
  });

  it("IRP 계좌만 있어도 카드를 표시한다", async () => {
    fetchPensionContribution.mockResolvedValue(makeStatus());
    renderWithProviders(<PensionContributionCard overview={makeOverview(["IRP"])} />);
    await waitFor(() => expect(screen.getByText(/연금저축·IRP 납입 현황/)).toBeInTheDocument());
  });

  it("embedded 모드에서는 카드 헤더/보더 없이 내용만 렌더한다", async () => {
    fetchPensionContribution.mockResolvedValue(makeStatus());
    const { container } = renderWithProviders(
      <PensionContributionCard overview={makeOverview(["PENSION_SAVINGS"])} embedded />,
    );
    await waitFor(() => expect(screen.getByText(/연금저축·IRP 납입 현황/)).toBeInTheDocument());
    expect(container.querySelector(".card")).toBeNull();
  });
});
