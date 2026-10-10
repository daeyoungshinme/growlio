import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import TradeFormModal from "@/components/assets/TradeFormModal";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { AssetAccount } from "@/api/assets";
import { createTrade, deleteTrade, fetchTrades, updateTrade } from "@/api/trades";

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

  const feeRecord = {
    id: "t5",
    account_id: "acc-1",
    side: "BUY" as const,
    ticker: "005930",
    market: "KOSPI",
    name: "삼성전자",
    qty: 1,
    price_krw: 70_000,
    fee: 300,
    trade_date: "2026-10-03",
    notes: "메모",
    created_at: "2026-10-03T00:00:00Z",
  };
  const renderWithRecord = () =>
    renderWithProviders(
      <TradeFormModal
        accounts={accounts}
        prefill={{ account_id: "acc-1", ticker: "005930", market: "KOSPI", name: "삼성전자" }}
        onClose={() => {}}
      />,
    );

  it("수정에서 수수료·메모를 비우면 null로 보내 기존 값을 지운다", async () => {
    vi.mocked(updateTrade)
      .mockReset()
      .mockResolvedValue({} as never);
    vi.mocked(fetchTrades).mockResolvedValue([feeRecord]);
    renderWithRecord();
    fireEvent.click(await screen.findByRole("button", { name: "2026-10-03 기록 수정" }));
    fireEvent.change(screen.getByLabelText("수수료 (원, 선택)"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText(/메모/), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "기록 수정" }));
    await waitFor(() => expect(vi.mocked(updateTrade)).toHaveBeenCalled());
    expect(vi.mocked(updateTrade).mock.calls[0][1]).toMatchObject({ fee: null, notes: null });
  });

  it("수정 중인 기록을 삭제하면 deleteTrade 호출 + 수정 모드 해제", async () => {
    vi.mocked(deleteTrade)
      .mockReset()
      .mockResolvedValue(undefined as never);
    vi.mocked(fetchTrades).mockResolvedValue([feeRecord]);
    renderWithRecord();
    fireEvent.click(await screen.findByRole("button", { name: "2026-10-03 기록 수정" }));
    expect(screen.getByRole("button", { name: "기록 수정" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "2026-10-03 기록 삭제" }));
    await waitFor(() => expect(vi.mocked(deleteTrade)).toHaveBeenCalled());
    expect(vi.mocked(deleteTrade).mock.calls[0][0]).toBe("t5");
    expect(screen.getByRole("button", { name: "기록 추가" })).toBeInTheDocument();
  });
});
