import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { AssetAccount } from "@/api/assets";

// PerAccountRebalancingAlertList가 실제로 받는 linkedAccounts를 검증하기 위해 얕은 스텁으로 대체.
vi.mock("@/components/portfolio-analysis/PerAccountRebalancingAlertList", () => ({
  default: ({ linkedAccounts }: { linkedAccounts: AssetAccount[] }) => (
    <ul>
      {linkedAccounts.map((a) => (
        <li key={a.id}>{a.name}</li>
      ))}
    </ul>
  ),
}));

vi.mock("@/components/rebalancing/RebalancingAlertModal", () => ({
  default: () => <div data-testid="aggregate-modal" />,
}));

import RebalancingAlertModalRouter from "@/components/rebalancing/RebalancingAlertModalRouter";

function account(overrides: Partial<AssetAccount>): AssetAccount {
  return {
    id: overrides.id ?? "acc",
    name: overrides.name ?? "계좌",
    is_active: true,
    ...overrides,
  } as AssetAccount;
}

describe("RebalancingAlertModalRouter", () => {
  beforeEach(() => vi.clearAllMocks());

  it("PER_ACCOUNT 스코프에서 은행/부동산 등 비주식 계좌는 계좌별 목록에서 제외한다", async () => {
    const accounts = [
      account({ id: "a1", name: "KIS 계좌", asset_type: "STOCK_KIS" }),
      account({ id: "a2", name: "키움 계좌", asset_type: "STOCK_KIWOOM" }),
      account({ id: "a3", name: "은행 계좌", asset_type: "BANK_ACCOUNT" }),
      account({ id: "a4", name: "부동산", asset_type: "REAL_ESTATE" }),
      account({ id: "a5", name: "비활성 KIS", asset_type: "STOCK_KIS", is_active: false }),
    ];

    renderWithProviders(
      <RebalancingAlertModalRouter
        portfolioId="port-1"
        portfolioName="테스트"
        alertScope="PER_ACCOUNT"
        accountIds={accounts.map((a) => a.id)}
        accounts={accounts}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByText("KIS 계좌")).toBeDefined());
    expect(screen.getByText("키움 계좌")).toBeDefined();
    expect(screen.queryByText("은행 계좌")).toBeNull();
    expect(screen.queryByText("부동산")).toBeNull();
    expect(screen.queryByText("비활성 KIS")).toBeNull();
  });

  it("alertScope가 AGGREGATE(또는 미지정)면 통합 모달을 렌더링한다", () => {
    renderWithProviders(
      <RebalancingAlertModalRouter
        portfolioId="port-1"
        portfolioName="테스트"
        accountIds={["a1"]}
        accounts={[account({ id: "a1" })]}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByTestId("aggregate-modal")).toBeDefined();
  });
});
