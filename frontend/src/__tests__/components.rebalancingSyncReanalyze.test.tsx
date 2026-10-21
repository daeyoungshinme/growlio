import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { AssetAccount } from "@/api/assets";
import type { ExecutionResult } from "@/api/rebalancing";

vi.mock("@/api/assets", () => ({ syncAccount: vi.fn() }));
vi.mock("@/utils/queryInvalidation", () => ({
  invalidateSyncData: vi.fn().mockResolvedValue(undefined),
}));

import { syncAccount } from "@/api/assets";
import { RebalancingAccountSyncSection } from "@/components/rebalancing/RebalancingAccountSyncSection";
import { RebalancingResultSection } from "@/components/rebalancing/RebalancingResultSection";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const kisAccount = {
  id: "acc1",
  name: "KIS",
  asset_type: "STOCK_KIS",
  data_source: "KIS_API",
} as unknown as AssetAccount;

const result: ExecutionResult = {
  account_id: "acc1",
  account_name: "KIS",
  is_mock: false,
  success_count: 1,
  fail_count: 0,
  orders: [],
} as unknown as ExecutionResult;

describe("동기화 후 재분석 단일화 (plans/63 P2-3·P3-1)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("분석 하단 계좌 동기화가 성공하면 바로 재분석한다", async () => {
    vi.mocked(syncAccount).mockResolvedValue({} as never);
    const onReanalyze = vi.fn();
    wrap(<RebalancingAccountSyncSection accounts={[kisAccount]} onReanalyze={onReanalyze} />);

    fireEvent.click(screen.getByText("선택 계좌 동기화 후 재분석"));

    await waitFor(() => expect(onReanalyze).toHaveBeenCalledTimes(1));
    expect(syncAccount).toHaveBeenCalledWith("acc1");
  });

  it("동기화가 실패하면 재분석하지 않는다", async () => {
    vi.mocked(syncAccount).mockRejectedValue(new Error("fail"));
    const onReanalyze = vi.fn();
    wrap(<RebalancingAccountSyncSection accounts={[kisAccount]} onReanalyze={onReanalyze} />);

    fireEvent.click(screen.getByText("선택 계좌 동기화 후 재분석"));

    expect(await screen.findByText("일부 동기화 실패")).toBeDefined();
    expect(onReanalyze).not.toHaveBeenCalled();
  });

  it("실행 결과 화면의 동기화도 성공하면 분석을 갱신한다", async () => {
    vi.mocked(syncAccount).mockResolvedValue({} as never);
    const onSynced = vi.fn();
    wrap(<RebalancingResultSection results={[result]} onSynced={onSynced} />);

    fireEvent.click(screen.getByText("계좌 동기화 후 다시 분석"));

    await waitFor(() => expect(onSynced).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("동기화 완료 — 분석을 갱신했어요")).toBeDefined();
  });
});
