import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import TradeFormModal from "@/components/assets/TradeFormModal";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { AssetAccount } from "@/api/assets";
import { createTrade, fetchTrades, updateTrade } from "@/api/trades";

vi.mock("../api/trades", () => ({
  createTrade: vi.fn(),
  deleteTrade: vi.fn(),
  fetchTrades: vi.fn(),
  updateTrade: vi.fn(),
}));

vi.mock("../context/ExchangeRateContext", () => ({
  useExchangeRateContext: () => ({ rate: 1400, isLoading: false, error: null }),
}));

vi.mock("../utils/queryInvalidation", () => ({
  invalidateTradeData: vi.fn(),
}));

vi.mock("../utils/toast", () => ({ toast: vi.fn() }));

const accounts = [{ id: "acc-1", name: "키움 일반", asset_type: "STOCK_KIWOOM" }] as AssetAccount[];

describe("TradeFormModal", () => {
  beforeEach(() => {
    vi.mocked(createTrade)
      .mockReset()
      .mockResolvedValue({} as never);
    vi.mocked(fetchTrades).mockReset().mockResolvedValue([]);
  });

  it("해외 종목은 USD 단가를 원화로 환산해 저장", async () => {
    renderWithProviders(
      <TradeFormModal
        accounts={accounts}
        prefill={{ account_id: "acc-1", ticker: "AAPL", market: "NASDAQ", name: "Apple" }}
        onClose={() => {}}
      />,
    );
    expect(screen.getByLabelText("단가 (USD)")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("수량"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("단가 (USD)"), { target: { value: "200" } });
    fireEvent.click(screen.getByRole("button", { name: "기록 추가" }));
    await waitFor(() => expect(vi.mocked(createTrade)).toHaveBeenCalled());
    expect(vi.mocked(createTrade).mock.calls[0][0]).toMatchObject({
      account_id: "acc-1",
      side: "BUY",
      ticker: "AAPL",
      market: "NASDAQ",
      qty: 2,
      price_krw: 280_000,
    });
  });

  it("종목 미선택이면 저장하지 않고 오류 표시", async () => {
    renderWithProviders(<TradeFormModal accounts={accounts} onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("수량"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("단가 (원)"), { target: { value: "1000" } });
    fireEvent.click(screen.getByRole("button", { name: "기록 추가" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("종목을 선택해주세요");
    expect(vi.mocked(createTrade)).not.toHaveBeenCalled();
  });

  it("기존 기록 목록 표시", async () => {
    vi.mocked(fetchTrades).mockResolvedValue([
      {
        id: "t1",
        account_id: "acc-1",
        side: "SELL",
        ticker: "005930",
        market: "KOSPI",
        name: "삼성전자",
        qty: 3,
        price_krw: 80_000,
        fee: null,
        trade_date: "2026-10-05",
        notes: null,
        created_at: "2026-10-05T00:00:00Z",
      },
    ]);
    renderWithProviders(
      <TradeFormModal
        accounts={accounts}
        prefill={{ account_id: "acc-1", ticker: "005930", market: "KOSPI", name: "삼성전자" }}
        onClose={() => {}}
      />,
    );
    expect(await screen.findByText("이 종목의 기록")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "2026-10-05 기록 삭제" })).toBeInTheDocument();
  });

  it("기존 기록을 수정하면 원화 단가 그대로 updateTrade를 호출한다 (해외도 USD 역환산 없음)", async () => {
    vi.mocked(updateTrade)
      .mockReset()
      .mockResolvedValue({} as never);
    vi.mocked(fetchTrades).mockResolvedValue([
      {
        id: "t9",
        account_id: "acc-1",
        side: "BUY",
        ticker: "AAPL",
        market: "NASDAQ",
        name: "Apple",
        qty: 2,
        price_krw: 280_000,
        fee: 100,
        trade_date: "2026-10-01",
        notes: null,
        created_at: "2026-10-01T00:00:00Z",
      },
    ]);
    renderWithProviders(
      <TradeFormModal
        accounts={accounts}
        prefill={{ account_id: "acc-1", ticker: "AAPL", market: "NASDAQ", name: "Apple" }}
        onClose={() => {}}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "2026-10-01 기록 수정" }));
    expect(screen.getByLabelText("단가 (원)")).toHaveValue(280000);
    fireEvent.change(screen.getByLabelText("수량"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "기록 수정" }));
    await waitFor(() => expect(vi.mocked(updateTrade)).toHaveBeenCalled());
    expect(vi.mocked(updateTrade).mock.calls[0]).toEqual([
      "t9",
      expect.objectContaining({ side: "BUY", qty: 3, price_krw: 280_000, fee: 100 }),
    ]);
    expect(vi.mocked(createTrade)).not.toHaveBeenCalled();
  });
});
