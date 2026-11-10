import { describe, it, expect, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { RebalancingAlertFormState } from "@/hooks/useRebalancingAlertForm";

vi.mock("@/api/portfolios", () => ({
  fetchPortfolios: vi.fn().mockResolvedValue([
    {
      id: "port-1",
      name: "적립",
      items: [
        { ticker: "069500", name: "KODEX 200", market: "KOSPI", weight: 60 },
        { ticker: "VOO", name: "VOO", market: "NYSE", weight: 40 },
      ],
      base_type: "STOCK_ONLY",
      sort_order: 0,
      created_at: "",
      updated_at: "",
    },
  ]),
}));
vi.mock("@/api/assets", () => ({
  fetchAccounts: vi.fn().mockResolvedValue([]),
  fetchExchangeRate: vi.fn().mockResolvedValue({ usd_krw: 1500 }),
}));

import { DcaAmountField } from "@/components/rebalancing/alertModal/DcaAmountField";

function makeForm(amount: number | null) {
  return {
    dcaAmountKrw: amount,
    setDcaAmountKrw: vi.fn(),
    accountId: "acc-1",
  } as unknown as RebalancingAlertFormState;
}

const account = { id: "acc-1", tax_type: "GENERAL" } as never;

describe("DcaAmountField (plans/120)", () => {
  it("금액을 목표 비중대로 나눈 미리보기와 환전 안내를 보여준다", async () => {
    renderWithProviders(
      <DcaAmountField
        form={makeForm(500_000)}
        portfolioId="port-1"
        autoExecutionAccounts={[account]}
      />,
    );

    expect(await screen.findByText("300,000원")).toBeDefined();
    expect(await screen.findByText(/≈ \$133\.33/)).toBeDefined();
    expect(screen.getByText(/매수일 전에 환전해 두세요/)).toBeDefined();
    expect(screen.getByText(/이 금액까지만/)).toBeDefined();
  });

  it("비워 두면 예수금 전체 안내를 보여주고, 입력하면 setDcaAmountKrw를 호출한다", () => {
    const form = makeForm(null);
    renderWithProviders(
      <DcaAmountField form={form} portfolioId="port-1" autoExecutionAccounts={[account]} />,
    );

    expect(screen.getByText(/예수금 전체로 목표 비중을 채웁니다/)).toBeDefined();
    fireEvent.change(screen.getByLabelText("매회 적립 금액"), { target: { value: "300000" } });
    expect(form.setDcaAmountKrw).toHaveBeenCalledWith(300_000);
  });

  it("최소 금액보다 작으면 경고한다", () => {
    renderWithProviders(
      <DcaAmountField form={makeForm(5_000)} portfolioId="port-1" autoExecutionAccounts={[]} />,
    );
    expect(screen.getByText(/10,000원 이상 입력해주세요/)).toBeDefined();
  });
});
