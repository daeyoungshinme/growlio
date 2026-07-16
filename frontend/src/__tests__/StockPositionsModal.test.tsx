import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import StockPositionsModal from "@/components/assets/StockPositionsModal";
import { api } from "@/api/client";
import { toast } from "@/utils/toast";

vi.mock("@/api/client", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() },
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
    vi.mocked(api.get).mockResolvedValue({ data: POSITIONS_RESPONSE });
  });

  it("저장 성공 시 성공 토스트를 띄우고 모달을 닫는다", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: POSITIONS_RESPONSE });
    const onClose = vi.fn();
    renderWithProviders(
      <StockPositionsModal accountId="acc-1" accountName="테스트 계좌" onClose={onClose} />,
    );

    await screen.findAllByDisplayValue("삼성전자");
    fireEvent.click(screen.getByText("저장"));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(toast).toHaveBeenCalledWith("저장되었습니다", "success");
    expect(api.put).toHaveBeenCalledWith(
      "/assets/acc-1/positions",
      expect.arrayContaining([expect.objectContaining({ ticker: "005930" })]),
    );
  });

  it("저장 실패 시 모달을 닫지 않고 에러 메시지를 표시한다", async () => {
    vi.mocked(api.put).mockRejectedValue({
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
});
