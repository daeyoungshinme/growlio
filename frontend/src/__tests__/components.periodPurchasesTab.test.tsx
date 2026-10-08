import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import PeriodPurchasesTab from "@/components/assets/PeriodPurchasesTab";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { AssetAccount } from "@/api/assets";
import type { PeriodPurchaseItem, PeriodPurchaseSummary } from "@/api/trades";
import { fetchPeriodPurchases } from "@/api/trades";

vi.mock("../api/trades", () => ({
  fetchPeriodPurchases: vi.fn(),
}));

vi.mock("../components/assets/TradeFormModal", () => ({
  default: ({ prefill }: { prefill: { ticker: string } | null }) => (
    <div data-testid="trade-modal">{prefill?.ticker ?? "new"}</div>
  ),
}));

const account = {
  id: "acc-1",
  name: "키움 일반",
  asset_type: "STOCK_KIWOOM",
} as AssetAccount;
const bank = { id: "acc-2", name: "은행", asset_type: "BANK_ACCOUNT" } as AssetAccount;

function item(overrides: Partial<PeriodPurchaseItem> = {}): PeriodPurchaseItem {
  return {
    account_id: "acc-1",
    account_name: "키움 일반",
    ticker: "005930",
    market: "KOSPI",
    name: "삼성전자",
    source: "ESTIMATED",
    bought_qty: 10,
    bought_amount_krw: 700_000,
    avg_buy_price_krw: 70_000,
    held_qty: 10,
    held_cost_krw: 700_000,
    current_price_krw: 77_000,
    value_krw: 770_000,
    unrealized_pnl_krw: 70_000,
    realized_pnl_krw: 0,
    total_pnl_krw: 70_000,
    cost_basis_krw: 700_000,
    return_pct: 10,
    first_buy_date: "2026-10-02",
    partially_sold: false,
    price_estimated: false,
    ...overrides,
  };
}

function summary(items: PeriodPurchaseItem[]): PeriodPurchaseSummary {
  return {
    start: "2026-10-01",
    end: "2026-10-08",
    items,
    summary: {
      bought_amount_krw: 700_000,
      held_cost_krw: 700_000,
      value_krw: 770_000,
      realized_pnl_krw: 0,
      total_pnl_krw: 70_000,
      return_pct: 10,
    },
    tracking_started: [],
  };
}

describe("PeriodPurchasesTab", () => {
  beforeEach(() => {
    vi.mocked(fetchPeriodPurchases).mockReset();
  });

  it("요약과 종목 행, 추정 배지·안내를 표시", async () => {
    vi.mocked(fetchPeriodPurchases).mockResolvedValue(summary([item()]));
    renderWithProviders(<PeriodPurchasesTab accounts={[account, bank]} />);
    expect(await screen.findByText("삼성전자")).toBeInTheDocument();
    // 배지 + 안내문 강조
    expect(screen.getAllByText("추정")).toHaveLength(2);
    expect(screen.getAllByText("+10.00%").length).toBeGreaterThan(0);
    expect(screen.getByText(/매일 저장되는 보유 수량/)).toBeInTheDocument();
    // 은행 계좌는 필터에 노출되지 않음
    expect(screen.queryByRole("option", { name: "은행" })).not.toBeInTheDocument();
  });

  it("수기 기록 항목은 '기록' 배지, 일부 매도 표시", async () => {
    vi.mocked(fetchPeriodPurchases).mockResolvedValue(
      summary([item({ source: "MANUAL", partially_sold: true, held_qty: 4 })]),
    );
    renderWithProviders(<PeriodPurchasesTab accounts={[account]} />);
    expect(await screen.findByText("기록")).toBeInTheDocument();
    expect(screen.getByText("일부 매도")).toBeInTheDocument();
    expect(screen.queryByText(/매일 저장되는 보유 수량/)).not.toBeInTheDocument();
  });

  it("빈 상태", async () => {
    vi.mocked(fetchPeriodPurchases).mockResolvedValue(summary([]));
    renderWithProviders(<PeriodPurchasesTab accounts={[account]} />);
    expect(await screen.findByText(/매수한 종목이 없습니다/)).toBeInTheDocument();
  });

  it("연간 전환 시 period=year로 조회", async () => {
    vi.mocked(fetchPeriodPurchases).mockResolvedValue(summary([]));
    renderWithProviders(<PeriodPurchasesTab accounts={[account]} />);
    await screen.findByText(/매수한 종목이 없습니다/);
    fireEvent.click(screen.getByRole("button", { name: "연간" }));
    await waitFor(() =>
      expect(vi.mocked(fetchPeriodPurchases)).toHaveBeenLastCalledWith(
        expect.objectContaining({ period: "year", month: undefined }),
      ),
    );
  });

  it("다음 기간 버튼은 현재 기간에서 비활성, 이전 기간 이동 가능", async () => {
    vi.mocked(fetchPeriodPurchases).mockResolvedValue(summary([]));
    renderWithProviders(<PeriodPurchasesTab accounts={[account]} />);
    await screen.findByText(/매수한 종목이 없습니다/);
    expect(screen.getByRole("button", { name: "다음 기간" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "이전 기간" }));
    expect(screen.getByRole("button", { name: "다음 기간" })).not.toBeDisabled();
  });

  it("직접 기록하기 → 종목이 채워진 기록 모달", async () => {
    vi.mocked(fetchPeriodPurchases).mockResolvedValue(summary([item()]));
    renderWithProviders(<PeriodPurchasesTab accounts={[account]} />);
    fireEvent.click(await screen.findByRole("button", { name: "직접 기록하기" }));
    expect(await screen.findByTestId("trade-modal")).toHaveTextContent("005930");
  });
});
