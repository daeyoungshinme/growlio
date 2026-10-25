import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import React from "react";

// ── mocks ────────────────────────────────────────────────────────────────────

vi.mock("@/hooks/useSelectedPortfolio", () => ({
  useSelectedPortfolio: () => ({ portfolios: [], anchoredIds: [], selectedId: undefined }),
}));

vi.mock("@/components/rebalancing/RecommendationCard", () => ({
  default: () => React.createElement("div", { "data-testid": "recommendation-card" }),
}));

// 청크 다운로드가 끝나지 않은 상태를 흉내 — 렌더 중 끝나지 않는 Promise로 suspend
const pending = new Promise<never>(() => {});
vi.mock("@/components/rebalancing/TacticalAllocationTab", () => ({
  default: () => {
    throw pending;
  },
}));

// ── imports ───────────────────────────────────────────────────────────────────

import GoalAdjustTab from "@/components/rebalancing/GoalAdjustTab";
import type { GoalMode } from "@/utils/rebalancingUrl";

// ── helpers ───────────────────────────────────────────────────────────────────

/** 실제 페이지처럼 모드를 URL에 두고 setSearchParams로 바꾼다(라우터가 startTransition으로 감쌈) */
function Harness() {
  const [params, setParams] = useSearchParams();
  const mode = (params.get("gmode") ?? "추천") as GoalMode;
  return (
    <GoalAdjustTab
      mode={mode}
      onModeChange={(m) => setParams({ gmode: m }, { replace: true })}
      onSelectPortfolio={() => {}}
      onGoToExecution={() => {}}
      onCreatePortfolio={() => {}}
      onCreateEmptyPortfolio={() => {}}
      initialRecOptionsOpen={false}
      onRecOptionsClosed={() => {}}
    />
  );
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe("GoalAdjustTab", () => {
  it("전술 청크가 아직 로딩 중이어도 탭 선택은 즉시 바뀌고 스켈레톤을 보여준다", async () => {
    render(
      <MemoryRouter initialEntries={["/rebalancing"]}>
        <Harness />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("recommendation-card")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: "전술" }));
    });

    expect(screen.getByRole("tab", { name: "전술" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByTestId("recommendation-card")).not.toBeInTheDocument();
    expect(screen.getByRole("status", { name: "로딩 중" })).toBeInTheDocument();
  });
});
