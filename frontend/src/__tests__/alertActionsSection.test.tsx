import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor, within } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { AlertActionsSection } from "@/components/rebalancing/alertModal/AlertActionsSection";
import type { RebalancingAlertFormState } from "@/hooks/useRebalancingAlertForm";

const mockCreatePlan = vi.fn();
vi.mock("@/api/rebalancing", () => ({
  createRebalancingExecutionPlan: (...args: unknown[]) => mockCreatePlan(...args),
}));
vi.mock("@/api/alerts", () => ({
  sendTestAccountRebalancingAlert: vi.fn(),
  sendTestRebalancingAlert: vi.fn(),
}));
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));
vi.mock("@/utils/queryInvalidation", () => ({ invalidateRebalancingPlanData: vi.fn() }));

// 이 섹션이 읽는 필드만 채운 최소 폼 상태
const autoForm = {
  mode: "AUTO",
  accountId: "acc-1",
  strategy: "FULL",
  orderType: "MARKET",
  isPending: false,
  upsertMut: { mutate: vi.fn(), isPending: false },
  deleteMut: { mutate: vi.fn(), isPending: false },
} as unknown as RebalancingAlertFormState;

describe("AlertActionsSection — 지금 계획 생성", () => {
  beforeEach(() => {
    mockCreatePlan.mockReset().mockResolvedValue({ status: "PLAN_GENERATED", message: "생성됨" });
  });

  it("한 번 탭으로 실행하지 않고, 자동 매수 고지 후 확인해야 계획을 만든다", async () => {
    renderWithProviders(<AlertActionsSection form={autoForm} hasAlert portfolioId="pf-1" />);

    fireEvent.click(screen.getByRole("button", { name: "지금 계획 생성" }));
    const dialog = screen.getByRole("dialog");
    expect(
      within(dialog).getByText(/매수는 설정된 대기시간이 지나면 자동으로 실행/),
    ).toBeInTheDocument();
    expect(mockCreatePlan).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "계획 생성" }));
    await waitFor(() => expect(mockCreatePlan).toHaveBeenCalledTimes(1));
    expect(mockCreatePlan.mock.calls[0][0]).toBe("pf-1");
  });

  it("확인창에서 취소하면 계획을 만들지 않는다", () => {
    renderWithProviders(<AlertActionsSection form={autoForm} hasAlert portfolioId="pf-1" />);

    fireEvent.click(screen.getByRole("button", { name: "지금 계획 생성" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "취소" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mockCreatePlan).not.toHaveBeenCalled();
  });
});
