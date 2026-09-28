import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import StockPositionsModal from "@/components/assets/StockPositionsModal";
import {
  fetchAccountPositions,
  replaceAccountPositions,
  syncAccountPositionPrices,
} from "@/api/assets";
import { toast } from "@/utils/toast";

vi.mock("@/api/assets", () => ({
  fetchAccountPositions: vi.fn(),
  replaceAccountPositions: vi.fn(),
  syncAccountPositionPrices: vi.fn(),
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

vi.mock("@/hooks/useExchangeRate", () => ({
  useExchangeRate: () => null,
}));

const POSITIONS_RESPONSE = {
  positions: [
    {
      ticker: "005930",
      name: "삼성전자",
      market: "KOSPI",
      qty: 10,
      avg_price: 50000,
      avg_price_usd: null,
      usd_rate: null,
      current_price: 60000,
      current_price_usd: null,
    },
  ],
  summary: { total_invested: 500000, total_value: 600000, total_pnl: 100000, total_pnl_pct: 20 },
};

describe("StockPositionsModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchAccountPositions).mockResolvedValue(POSITIONS_RESPONSE);
  });

  it("저장 성공 시 성공 토스트를 띄우고 모달을 닫는다", async () => {
    vi.mocked(replaceAccountPositions).mockResolvedValue(undefined);
    const onClose = vi.fn();
    renderWithProviders(
      <StockPositionsModal accountId="acc-1" accountName="테스트 계좌" onClose={onClose} />,
    );

    await screen.findAllByDisplayValue("삼성전자");
    fireEvent.click(screen.getByText("저장"));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(toast).toHaveBeenCalledWith("저장되었습니다", "success");
    expect(replaceAccountPositions).toHaveBeenCalledWith(
      "acc-1",
      expect.arrayContaining([expect.objectContaining({ ticker: "005930" })]),
    );
  });

  it("저장 실패 시 모달을 닫지 않고 에러 메시지를 표시한다", async () => {
    vi.mocked(replaceAccountPositions).mockRejectedValue({
      response: { data: { detail: "저장 중 오류가 발생했습니다" } },
    });
    const onClose = vi.fn();
    renderWithProviders(
      <StockPositionsModal accountId="acc-1" accountName="테스트 계좌" onClose={onClose} />,
    );

    await screen.findAllByDisplayValue("삼성전자");
    fireEvent.click(screen.getByText("저장"));

    await waitFor(() =>
      expect(screen.getByText("저장 중 오류가 발생했습니다")).toBeInTheDocument(),
    );
    expect(onClose).not.toHaveBeenCalled();
  });

  it("현재가 동기화 결과로 행과 요약을 갱신한다", async () => {
    vi.mocked(syncAccountPositionPrices).mockResolvedValue({
      ...POSITIONS_RESPONSE,
      positions: [{ ...POSITIONS_RESPONSE.positions[0], name: "삼성전자우" }],
    });
    renderWithProviders(
      <StockPositionsModal accountId="acc-1" accountName="테스트 계좌" onClose={vi.fn()} />,
    );

    await screen.findAllByDisplayValue("삼성전자");
    fireEvent.click(screen.getByRole("button", { name: /현재가/ }));

    await screen.findAllByDisplayValue("삼성전자우");
    expect(syncAccountPositionPrices).toHaveBeenCalledWith("acc-1");
  });
});
