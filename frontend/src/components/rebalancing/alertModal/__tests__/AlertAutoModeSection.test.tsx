import { act, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RebalancingAlertFormState } from "@/hooks/useRebalancingAlertForm";
import { AlertAutoModeSection } from "../AlertAutoModeSection";

vi.mock("@/api/queryOptions", () => ({
  settingsQuery: { queryKey: ["settings-test"], queryFn: () => new Promise(() => {}) },
}));
vi.mock("../AutoExecutionAccountPicker", () => ({ default: () => <div>account-picker</div> }));
vi.mock("../AutoDailyCapEditor", () => ({ AutoDailyCapEditor: () => null }));

/** 이 테스트가 보지 않는 필드는 setter면 mock, 값이면 빈 값 — 폼 상태 전체를 손으로 채우지 않는다 */
const form = new Proxy({} as Record<string, unknown>, {
  get: (target, key: string) => {
    if (!(key in target)) target[key] = key.startsWith("set") ? vi.fn() : "";
    return target[key];
  },
}) as unknown as RebalancingAlertFormState;

function renderSection(mutate = vi.fn(), isPending = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <AlertAutoModeSection
        form={form}
        autoExecutionAccounts={[]}
        canSwitchToPerAccount
        switchToPerAccountMut={{ mutate, isPending }}
      />
    </QueryClientProvider>,
  );
  return mutate;
}

describe("AlertAutoModeSection 계좌별 전환 2단계 확인 (plans/156 D)", () => {
  afterEach(() => vi.useRealTimers());

  it("처음 누르면 확인 문구만 보이고, 한 번 더 눌러야 전환한다", () => {
    const mutate = renderSection();

    fireEvent.click(screen.getByText("여러 계좌에 각각 자동 실행 설정하기 →"));
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByText(/지금 설정은 삭제되고/)).toBeDefined();

    fireEvent.click(screen.getByText(/한 번 더 눌러 전환/));
    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it("3초 안에 다시 누르지 않으면 확인 상태가 풀린다", () => {
    vi.useFakeTimers();
    const mutate = renderSection();

    fireEvent.click(screen.getByText("여러 계좌에 각각 자동 실행 설정하기 →"));
    act(() => {
      vi.advanceTimersByTime(3000);
    });

    expect(screen.getByText("여러 계좌에 각각 자동 실행 설정하기 →")).toBeDefined();
    fireEvent.click(screen.getByText("여러 계좌에 각각 자동 실행 설정하기 →"));
    expect(mutate).not.toHaveBeenCalled();
  });

  it("전환 중에는 버튼을 막는다", () => {
    renderSection(vi.fn(), true);
    const button = screen.getByText(/여러 계좌에 각각/).closest("button");
    expect(button?.disabled).toBe(true);
  });
});
