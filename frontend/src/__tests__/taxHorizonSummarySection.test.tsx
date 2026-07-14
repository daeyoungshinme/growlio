import { describe, it, expect, vi, afterEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { IsaStatusSummary } from "@/api/tax";
import type { PortfolioOverview } from "@/types";

const fetchIsaStatus = vi.fn();
const fetchPensionContribution = vi.fn();

vi.mock("@/api/tax", () => ({
  fetchIsaStatus: (...args: unknown[]) => fetchIsaStatus(...args),
  fetchPensionContribution: (...args: unknown[]) => fetchPensionContribution(...args),
}));

import TaxHorizonSummarySection from "@/components/dashboard/TaxHorizonSummarySection";

function setViewportWidth(width: number) {
  Object.defineProperty(window, "innerWidth", { writable: true, configurable: true, value: width });
}

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

describe("TaxHorizonSummarySection", () => {
  afterEach(() => {
    setViewportWidth(1024);
  });

  it("투자기간/ISA/연금 태그가 하나도 없으면 렌더링하지 않는다", async () => {
    fetchIsaStatus.mockResolvedValue(emptyIsa);
    const { container } = renderWithProviders(
      <TaxHorizonSummarySection overview={makeOverview([{ tax_type: "GENERAL" }])} />,
    );
    await waitFor(() => expect(fetchIsaStatus).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("투자기간 태그가 있으면 카드를 렌더링한다 (데스크탑 기본 펼침)", async () => {
    setViewportWidth(1280);
    fetchIsaStatus.mockResolvedValue(emptyIsa);
    renderWithProviders(
      <TaxHorizonSummarySection overview={makeOverview([{ investment_horizon: "LONG_TERM" }])} />,
    );
    expect(await screen.findByText("세제·기간 현황")).toBeInTheDocument();
    expect(await screen.findByText(/투자기간별 자산현황/)).toBeInTheDocument();
  });

  it("모바일 뷰포트에서는 기본 접힘 상태로 시작하고, 토글 클릭 시 펼쳐진다", async () => {
    setViewportWidth(375);
    fetchIsaStatus.mockResolvedValue(emptyIsa);
    renderWithProviders(
      <TaxHorizonSummarySection overview={makeOverview([{ investment_horizon: "LONG_TERM" }])} />,
    );
    await screen.findByText("세제·기간 현황");
    expect(screen.queryByText(/투자기간별 자산현황/)).toBeNull();

    fireEvent.click(screen.getByText("세제·기간 현황"));
    expect(await screen.findByText(/투자기간별 자산현황/)).toBeInTheDocument();
  });

  it("ISA 계좌가 있으면 IsaMaturityCard를 임베드 렌더한다", async () => {
    setViewportWidth(1280);
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
    renderWithProviders(<TaxHorizonSummarySection overview={makeOverview([])} />);
    expect(await screen.findByText("ISA 만기·세제 현황")).toBeInTheDocument();
  });

  it("연금저축 태그가 있으면 PensionContributionCard를 임베드 렌더한다", async () => {
    setViewportWidth(1280);
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
    renderWithProviders(
      <TaxHorizonSummarySection overview={makeOverview([{ tax_type: "PENSION_SAVINGS" }])} />,
    );
    expect(await screen.findByText(/연금저축·IRP 납입 현황/)).toBeInTheDocument();
  });
});
