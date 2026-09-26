import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/client", () => {
  const mockApi = { get: vi.fn(), put: vi.fn() };
  return {
    api: mockApi,
    apiGet: (url: string, ...args: unknown[]) =>
      mockApi.get(url, ...args).then((r: { data: unknown }) => r.data),
    apiPut: (url: string, ...args: unknown[]) =>
      mockApi.put(url, ...args).then((r: { data: unknown }) => r.data),
  };
});
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

import { AutoDailyCapEditor } from "@/components/rebalancing/alertModal/AutoDailyCapEditor";
import { api } from "@/api/client";

function renderWithSettings(dailyCap: number | null) {
  vi.mocked(api.get).mockResolvedValue({
    data: {
      auto_rebalancing_daily_value_cap_krw: dailyCap,
      auto_rebalancing_max_order_value_krw: 50_000_000,
    },
  });
  vi.mocked(api.put).mockResolvedValue({ data: { detail: "ok" } });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AutoDailyCapEditor />
    </QueryClientProvider>,
  );
}

describe("AutoDailyCapEditor", () => {
  beforeEach(() => vi.clearAllMocks());

  it("미설정이면 무제한으로 표시하고 해제 버튼을 숨긴다", async () => {
    renderWithSettings(null);
    expect(await screen.findByText(/현재: 무제한/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "한도 해제" })).not.toBeInTheDocument();
    // 변경 전에는 저장 비활성
    expect(screen.getByRole("button", { name: "저장" })).toBeDisabled();
  });

  it("금액을 입력해 저장하면 숫자로 PUT 한다", async () => {
    renderWithSettings(null);
    const input = await screen.findByLabelText("하루 합산 최대 거래대금 (원)");
    fireEvent.change(input, { target: { value: "3000000" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith("/settings/auto-rebalancing-daily-cap", {
        daily_value_cap_krw: 3_000_000,
      }),
    );
  });

  it("단위 버튼으로 금액을 더할 수 있다", async () => {
    renderWithSettings(null);
    const input = await screen.findByLabelText("하루 합산 최대 거래대금 (원)");
    fireEvent.click(screen.getByRole("button", { name: "+100만" }));
    fireEvent.click(screen.getByRole("button", { name: "+100만" }));
    expect(input).toHaveValue(2_000_000);
  });

  it("0 이하는 오류를 표시하고 저장을 막는다", async () => {
    renderWithSettings(null);
    const input = await screen.findByLabelText("하루 합산 최대 거래대금 (원)");
    fireEvent.change(input, { target: { value: "0" } });
    expect(screen.getByText("0보다 큰 금액을 입력하세요.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "저장" })).toBeDisabled();
  });

  it("설정된 한도가 있으면 해제 시 null로 PUT 한다", async () => {
    renderWithSettings(5_000_000);
    const input = await screen.findByLabelText("하루 합산 최대 거래대금 (원)");
    expect(input).toHaveValue(5_000_000);
    fireEvent.click(screen.getByRole("button", { name: "한도 해제" }));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith("/settings/auto-rebalancing-daily-cap", {
        daily_value_cap_krw: null,
      }),
    );
  });
});
