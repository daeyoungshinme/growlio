import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/client", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() },
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
}));
vi.mock("@/hooks/useExchangeRate", () => ({ useExchangeRate: vi.fn(() => 1350) }));
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

import StockAccountModal from "@/components/assets/StockAccountModal";
import type { AssetAccount } from "@/api/assets";

function makeAccount(overrides: Partial<AssetAccount>): AssetAccount {
  return {
    id: "acc-1",
    name: "키움 계좌",
    asset_type: "STOCK_KIWOOM",
    data_source: "KIWOOM_API",
    institution: "키움증권",
    kis_account_no: null,
    kiwoom_account_no: "12345678-01",
    is_mock_mode: false,
    manual_amount: null,
    manual_currency: "KRW",
    manual_updated_at: null,
    deposit_krw: null,
    deposit_usd: null,
    real_estate_details: null,
    include_in_total: true,
    is_active: true,
    sort_order: 0,
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    has_own_kis_credentials: false,
    has_own_kiwoom_credentials: true,
    has_own_toss_credentials: false,
    ...overrides,
  };
}

function renderModal(initialAccount: AssetAccount, onSubmit = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <StockAccountModal
        initialAccount={initialAccount}
        onClose={vi.fn()}
        onSubmit={onSubmit}
        isLoading={false}
      />
    </QueryClientProvider>,
  );
  return onSubmit;
}

describe("StockAccountModal — 키움 원화주문", () => {
  beforeEach(() => vi.clearAllMocks());

  it("키움 계좌에서 원화주문 표시를 켜고 저장하면 함께 보낸다", () => {
    const onSubmit = renderModal(makeAccount({}));
    const checkbox = screen.getByLabelText("원화주문 서비스 신청 계좌");
    expect(checkbox).not.toBeChecked();
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ krw_overseas_order: true }));
  });

  it("저장된 값을 불러온다", () => {
    renderModal(makeAccount({ krw_overseas_order: true }));
    expect(screen.getByLabelText("원화주문 서비스 신청 계좌")).toBeChecked();
  });

  it("키움 외 계좌에는 보이지 않고 보내지도 않는다", () => {
    const onSubmit = renderModal(
      makeAccount({
        asset_type: "STOCK_KIS",
        data_source: "KIS_API",
        kis_account_no: "12345678-01",
        kiwoom_account_no: null,
        has_own_kis_credentials: true,
        has_own_kiwoom_credentials: false,
      }),
    );
    expect(screen.queryByLabelText("원화주문 서비스 신청 계좌")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(onSubmit.mock.calls[0]?.[0]).not.toHaveProperty("krw_overseas_order", true);
  });
});
