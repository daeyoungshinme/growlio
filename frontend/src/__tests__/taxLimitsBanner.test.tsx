import { describe, it, expect, vi } from "vitest";
import { screen, waitFor, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { IsaStatusSummary, TaxSummary } from "@/api/tax";
import type { PortfolioOverview } from "@/types";
import { fmtKrw } from "@/utils/format";

const fetchIsaStatus = vi.fn();
const fetchPensionContribution = vi.fn();
const fetchTaxSummary = vi.fn();

vi.mock("@/api/tax", () => ({
  fetchIsaStatus: (...args: unknown[]) => fetchIsaStatus(...args),
  fetchPensionContribution: (...args: unknown[]) => fetchPensionContribution(...args),
  fetchTaxSummary: (...args: unknown[]) => fetchTaxSummary(...args),
}));

import TaxLimitsBanner from "@/components/dashboard/TaxLimitsBanner";

function renderBanner(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>,
  );
}

function makeOverview(accounts: Array<{ tax_type?: string | null }>): PortfolioOverview {
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

const emptyTaxSummary: TaxSummary = {
  year: 2026,
  dividend_income_krw: 0,
  dividend_tax_krw: 0,
  overseas_unrealized_gain_krw: 0,
  overseas_gain_deduction_krw: 0,
  overseas_tax_estimated_krw: 0,
  domestic_stock_value_krw: 0,
  domestic_unrealized_gain_krw: 0,
  domestic_large_holder_warning: false,
  domestic_large_holder_excess_krw: 0,
  comprehensive_tax_warning: false,
  comprehensive_tax_remaining_krw: 20_000_000,
  total_estimated_tax_krw: 0,
  total_fees_krw: 0,
  harvesting_recommendations: [],
  financial_investment_tax_simulation: {} as TaxSummary["financial_investment_tax_simulation"],
  note: "",
  rates: { dividend_tax_rate_pct: 15.4, overseas_tax_rate_pct: 22 },
};

describe("TaxLimitsBanner", () => {
  it("ISA/연금 계좌가 하나도 없고 세금 추정액도 없으면 렌더링하지 않는다", async () => {
    fetchIsaStatus.mockResolvedValue(emptyIsa);
    fetchTaxSummary.mockResolvedValue(emptyTaxSummary);
    const { container } = renderBanner(
      <TaxLimitsBanner overview={makeOverview([{ tax_type: "GENERAL" }])} />,
    );
    await waitFor(() => expect(fetchIsaStatus).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("가장 임박한 ISA 만기 D-day를 표시한다", async () => {
    fetchTaxSummary.mockResolvedValue(emptyTaxSummary);
    fetchIsaStatus.mockResolvedValue({
      accounts: [
        {
          account_id: "acc1",
          account_name: "일반형 ISA",
          isa_type: "GENERAL",
          isa_open_date: "2023-01-01",
          maturity_date: "2026-09-01",
          is_mature: false,
          days_remaining: 45,
          needs_open_date: false,
          estimated_cumulative_pnl_krw: 500_000,
          is_manual_override: false,
          tax_free_limit_krw: 2_000_000,
          taxable_excess_krw: 0,
          estimated_tax_krw: 0,
        },
      ],
      note: "",
    } as IsaStatusSummary);

    renderBanner(<TaxLimitsBanner overview={makeOverview([])} />);
    expect(await screen.findByText("ISA D-45")).toBeInTheDocument();
  });

  it("한도 초과 계좌가 있으면 D-day 대신 한도초과 건수를 우선 표시한다", async () => {
    fetchTaxSummary.mockResolvedValue(emptyTaxSummary);
    fetchIsaStatus.mockResolvedValue({
      accounts: [
        {
          account_id: "acc1",
          account_name: "일반형 ISA",
          isa_type: "GENERAL",
          isa_open_date: "2023-01-01",
          maturity_date: "2026-09-01",
          is_mature: false,
          days_remaining: 45,
          needs_open_date: false,
          estimated_cumulative_pnl_krw: 3_000_000,
          is_manual_override: false,
          tax_free_limit_krw: 2_000_000,
          taxable_excess_krw: 1_000_000,
          estimated_tax_krw: 99_000,
        },
      ],
      note: "",
    } as IsaStatusSummary);

    renderBanner(<TaxLimitsBanner overview={makeOverview([])} />);
    expect(await screen.findByText("ISA 한도초과 1건")).toBeInTheDocument();
    expect(screen.queryByText("ISA D-45")).toBeNull();
  });

  it("연금저축 태그 계좌가 있으면 공제한도 달성률을 표시하고, 자산탭 세금 탭으로 딥링크한다", async () => {
    fetchTaxSummary.mockResolvedValue(emptyTaxSummary);
    fetchIsaStatus.mockResolvedValue(emptyIsa);
    fetchPensionContribution.mockResolvedValue({
      year: 2026,
      pension_savings_deposit_krw: 3_000_000,
      irp_deposit_krw: 0,
      total_deposit_krw: 3_000_000,
      pension_savings_limit_krw: 6_000_000,
      total_limit_krw: 9_000_000,
      pension_savings_achievement_pct: 50.0,
      total_achievement_pct: 62.0,
      pension_savings_remaining_krw: 3_000_000,
      total_remaining_krw: 6_000_000,
      note: "",
    });

    renderBanner(<TaxLimitsBanner overview={makeOverview([{ tax_type: "PENSION_SAVINGS" }])} />);
    expect(await screen.findByText("연금공제 62% 달성")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "/assets?tab=투자현황&portfolioTab=세금",
    );
  });

  it("금융소득 종합과세 경고가 있으면 경고 문구를 표시한다", async () => {
    fetchIsaStatus.mockResolvedValue(emptyIsa);
    fetchTaxSummary.mockResolvedValue({
      ...emptyTaxSummary,
      comprehensive_tax_warning: true,
      total_estimated_tax_krw: 1_320_000,
    });

    renderBanner(<TaxLimitsBanner overview={makeOverview([])} />);
    expect(await screen.findByText("금융소득 종합과세 대상 가능")).toBeInTheDocument();
    expect(screen.getByText(`예상세금 ${fmtKrw(1_320_000)}`)).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "/assets?tab=투자현황&portfolioTab=세금",
    );
  });

  it("ISA/연금 계좌가 없어도 예상 세금이 있으면 배너를 렌더링한다", async () => {
    fetchIsaStatus.mockResolvedValue(emptyIsa);
    fetchTaxSummary.mockResolvedValue({
      ...emptyTaxSummary,
      total_estimated_tax_krw: 500_000,
    });

    const { container } = renderBanner(
      <TaxLimitsBanner overview={makeOverview([{ tax_type: "GENERAL" }])} />,
    );
    expect(await screen.findByText(`예상세금 ${fmtKrw(500_000)}`)).toBeInTheDocument();
    expect(container).not.toBeEmptyDOMElement();
  });
});
