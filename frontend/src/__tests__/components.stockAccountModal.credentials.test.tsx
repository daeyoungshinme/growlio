import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/client", () => {
  const mockApi = { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() };
  return {
    api: mockApi,
    apiGet: (url: string, ...args: unknown[]) =>
      mockApi.get(url, ...args).then((r: { data: unknown }) => r.data),
    apiPost: (url: string, ...args: unknown[]) =>
      mockApi.post(url, ...args).then((r: { data: unknown }) => r.data),
    apiPut: (url: string, ...args: unknown[]) =>
      mockApi.put(url, ...args).then((r: { data: unknown }) => r.data),
    apiPatch: (url: string, ...args: unknown[]) =>
      mockApi.patch(url, ...args).then((r: { data: unknown }) => r.data),
    apiDelete: (url: string, ...args: unknown[]) =>
      mockApi.delete(url, ...args).then((r: { data: unknown }) => r.data),
  };
});
vi.mock("@/hooks/useExchangeRate", () => ({ useExchangeRate: vi.fn(() => 1350) }));
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

import StockAccountModal from "@/components/assets/StockAccountModal";
import type { AssetAccount } from "@/api/assets";
import { api } from "@/api/client";

function renderModal(initialAccount?: AssetAccount) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StockAccountModal
        initialAccount={initialAccount}
        onClose={vi.fn()}
        onSubmit={vi.fn()}
        isLoading={false}
      />
    </QueryClientProvider>,
  );
}

/** 계좌 모달(바깥 dialog) 위에 뜬 연동 해제 확인 dialog */
function confirmDialog(): HTMLElement {
  // ConfirmModal은 계좌 모달 DOM 안에 렌더되므로 텍스트가 겹친다 — 가장 안쪽(마지막) dialog를 고른다
  const matches = screen
    .getAllByRole("dialog")
    .filter((d) => d.textContent?.includes("API 키를 삭제할까요"));
  const dialog = matches[matches.length - 1];
  if (!dialog) throw new Error("confirm dialog not found");
  return dialog;
}

function makeAccount(overrides: Partial<AssetAccount>): AssetAccount {
  return {
    id: "acc-1",
    name: "테스트 계좌",
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

describe("StockAccountModal — 키움 자격증명 검증", () => {
  beforeEach(() => vi.clearAllMocks());

  function byId(id: string): HTMLElement {
    const el = document.getElementById(id);
    if (!el) throw new Error(`#${id} not found`);
    return el;
  }

  function fillKiwoomCreate() {
    fireEvent.change(byId("stock-name"), { target: { value: "키움" } });
    fireEvent.change(byId("stock-data-source"), { target: { value: "KIWOOM_API" } });
    fireEvent.change(byId("stock-kiwoom-account-no"), { target: { value: "12345678-01" } });
    fireEvent.change(byId("stock-kiwoom-app-key"), { target: { value: "key" } });
    fireEvent.change(byId("stock-kiwoom-app-secret"), { target: { value: "secret" } });
  }

  it("검증 전에는 등록이 막히고, 검증 성공 후 등록할 수 있다", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { valid: true, message: "ok" } });
    renderModal();
    fillKiwoomCreate();

    expect(screen.getByRole("button", { name: "등록" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "자격증명 확인" }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/assets/verify-kiwoom-credentials", {
        kiwoom_app_key: "key",
        kiwoom_app_secret: "secret",
        is_mock: true,
      }),
    );
    expect(await screen.findByText("자격증명 확인됨")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "등록" })).toBeEnabled();
  });

  it("검증 후 키를 바꾸면 다시 검증해야 한다", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { valid: true, message: "ok" } });
    renderModal();
    fillKiwoomCreate();
    fireEvent.click(screen.getByRole("button", { name: "자격증명 확인" }));
    await screen.findByText("자격증명 확인됨");

    fireEvent.change(byId("stock-kiwoom-app-key"), { target: { value: "other" } });
    expect(screen.queryByText("자격증명 확인됨")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "등록" })).toBeDisabled();
  });
  it("키 검증을 통과해도 계좌번호가 비어 있으면 등록할 수 없다", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { valid: true, message: "ok" } });
    renderModal();
    fillKiwoomCreate();
    fireEvent.change(byId("stock-kiwoom-account-no"), { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "자격증명 확인" }));
    await screen.findByText("자격증명 확인됨");

    expect(screen.getByRole("button", { name: "등록" })).toBeDisabled();
    fireEvent.change(byId("stock-kiwoom-account-no"), { target: { value: "12345678-01" } });
    expect(screen.getByRole("button", { name: "등록" })).toBeEnabled();
  });
});

describe("StockAccountModal — 연동 해제", () => {
  beforeEach(() => vi.clearAllMocks());

  it("계좌별 키움 키가 있으면 확인 후 DELETE 한다", async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: null });
    renderModal(makeAccount({}));

    fireEvent.click(screen.getByRole("button", { name: /저장된 키움 API 키 삭제/ }));
    expect(confirmDialog()).toHaveTextContent("자동 동기화·자동 매매가 중단됩니다");
    fireEvent.click(within(confirmDialog()).getByRole("button", { name: "삭제" }));

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith("/assets/acc-1/kiwoom-credentials"),
    );
    expect(await screen.findByText(/API 키를 삭제했습니다/)).toBeInTheDocument();
  });

  it("취소하면 호출하지 않는다", () => {
    renderModal(makeAccount({}));
    fireEvent.click(screen.getByRole("button", { name: /저장된 키움 API 키 삭제/ }));
    fireEvent.click(within(confirmDialog()).getByRole("button", { name: "취소" }));
    expect(screen.queryByText(/API 키를 삭제할까요/)).not.toBeInTheDocument();
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("KIS 계좌가 공통 키를 쓰면(계좌별 키 없음) 버튼을 숨긴다", () => {
    renderModal(
      makeAccount({
        data_source: "KIS_API",
        asset_type: "STOCK_KIS",
        kis_account_no: "12345678-01",
        kiwoom_account_no: null,
        has_own_kis_credentials: false,
        has_own_kiwoom_credentials: false,
      }),
    );
    expect(screen.queryByRole("button", { name: /API 키 삭제/ })).not.toBeInTheDocument();
  });
});
