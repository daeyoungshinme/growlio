import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import TradeFormModal from "@/components/assets/TradeFormModal";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { AssetAccount } from "@/api/assets";
import { fetchAllTrades } from "@/api/trades";

vi.mock("../api/trades", () => ({
  createTrade: vi.fn(),
  deleteTrade: vi.fn(),
  fetchAllTrades: vi.fn(),
  updateTrade: vi.fn(),
}));

vi.mock("../context/ExchangeRateContext", () => ({
  useExchangeRateContext: () => ({ rate: 1400, isLoading: false, error: null }),
}));

vi.mock("../utils/queryInvalidation", () => ({ invalidateTradeData: vi.fn() }));
vi.mock("../utils/toast", () => ({ toast: vi.fn() }));

vi.mock("../hooks/useStockSearch", () => ({
  useStockSearch: () => ({
    suggestions: [{ ticker: "005930", market: "KOSPI", name: "삼성전자" }],
    isSearching: false,
    search: vi.fn(),
    clearSuggestions: vi.fn(),
  }),
}));

const accounts = [
  { id: "acc-1", name: "키움 일반", asset_type: "STOCK_KIWOOM" },
  { id: "acc-2", name: "토스 일반", asset_type: "STOCK_TOSS" },
] as AssetAccount[];

describe("TradeFormModal 계좌 변경", () => {
  it("수정 중 계좌를 바꾸면 수정 모드를 끝낸다 — 옛 계좌 기록을 고치지 않게(plans/118 C4)", async () => {
    vi.mocked(fetchAllTrades).mockResolvedValue([
      {
        id: "t1",
        account_id: "acc-1",
        side: "BUY",
        ticker: "005930",
        market: "KOSPI",
        name: "삼성전자",
        qty: 1,
        price_krw: 70_000,
        fee: null,
        trade_date: "2026-10-03",
        notes: null,
        created_at: "2026-10-03T00:00:00Z",
      },
    ]);
    renderWithProviders(<TradeFormModal accounts={accounts} onClose={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /삼성전자/ }));
    fireEvent.click(await screen.findByRole("button", { name: "2026-10-03 기록 수정" }));
    expect(screen.getByRole("button", { name: "기록 수정" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("계좌"), { target: { value: "acc-2" } });

    expect(screen.queryByRole("button", { name: "기록 수정" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "기록 추가" })).toBeInTheDocument();
  });
});
