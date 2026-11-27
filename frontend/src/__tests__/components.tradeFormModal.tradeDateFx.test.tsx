import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import TradeFormModal from "@/components/assets/TradeFormModal";
import { renderWithProviders } from "@/test/renderWithProviders";
import { fetchUsdKrwOn, type AssetAccount } from "@/api/assets";
import { createTrade, fetchAllTrades } from "@/api/trades";

// 지난 해외 거래는 거래일 환율로 환산한다 — 오늘 환율 고정이면 양도세 실현손익이 환율 변동만큼 틀어진다 (plans/156)
vi.mock("../api/trades", () => ({
  createTrade: vi.fn(),
  deleteTrade: vi.fn(),
  fetchAllTrades: vi.fn(),
  updateTrade: vi.fn(),
}));
vi.mock("../api/assets", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/assets")>()),
  fetchUsdKrwOn: vi.fn(),
}));
vi.mock("../context/ExchangeRateContext", () => ({
  useExchangeRateContext: () => ({ rate: 1400, isLoading: false, error: null }),
}));
vi.mock("../utils/queryInvalidation", () => ({ invalidateTradeData: vi.fn() }));
vi.mock("../utils/toast", () => ({ toast: vi.fn() }));

const accounts = [{ id: "acc-1", name: "키움 일반", asset_type: "STOCK_KIWOOM" }] as AssetAccount[];

function fillPastOverseasTrade() {
  renderWithProviders(
    <TradeFormModal
      accounts={accounts}
      prefill={{ account_id: "acc-1", ticker: "AAPL", market: "NASDAQ", name: "Apple" }}
      onClose={() => {}}
    />,
  );
  fireEvent.change(screen.getByLabelText("거래일"), { target: { value: "2026-05-09" } });
  fireEvent.change(screen.getByLabelText("수량"), { target: { value: "2" } });
  fireEvent.change(screen.getByLabelText("단가 (USD)"), { target: { value: "200" } });
}

describe("TradeFormModal 거래일 환율", () => {
  beforeEach(() => {
    vi.mocked(createTrade)
      .mockReset()
      .mockResolvedValue({} as never);
    vi.mocked(fetchAllTrades).mockReset().mockResolvedValue([]);
    vi.mocked(fetchUsdKrwOn).mockReset();
  });

  it("지난 거래일이면 그날 종가 환율로 환산해 저장한다", async () => {
    vi.mocked(fetchUsdKrwOn).mockResolvedValue({ usd_krw: 1300, rate_date: "2026-05-08" });
    fillPastOverseasTrade();

    expect(await screen.findByText(/2026-05-08 종가 환율/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "기록 추가" }));

    await waitFor(() => expect(vi.mocked(createTrade)).toHaveBeenCalled());
    expect(vi.mocked(fetchUsdKrwOn)).toHaveBeenCalledWith("2026-05-09");
    expect(vi.mocked(createTrade).mock.calls[0]![0]).toMatchObject({
      trade_date: "2026-05-09",
      price_krw: 260_000, // 200 × 1300 (현재 1400이 아니라)
    });
  });

  it("거래일 환율을 못 받으면 현재 환율로 대신하고 그렇게 알린다", async () => {
    vi.mocked(fetchUsdKrwOn).mockResolvedValue({ usd_krw: null, rate_date: null });
    fillPastOverseasTrade();

    expect(await screen.findByText(/거래일 환율을 못 받아 현재 환율/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "기록 추가" }));

    await waitFor(() => expect(vi.mocked(createTrade)).toHaveBeenCalled());
    expect(vi.mocked(createTrade).mock.calls[0]![0]).toMatchObject({ price_krw: 280_000 });
  });
});
