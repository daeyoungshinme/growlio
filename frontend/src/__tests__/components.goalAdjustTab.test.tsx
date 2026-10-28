import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import React from "react";

// ── mocks ────────────────────────────────────────────────────────────────────

const selection = vi.hoisted(() => ({
  current: {
    portfolios: [] as { id: string; name: string }[],
    tacticalIds: [] as string[],
    selectedId: undefined as string | undefined,
    tacticalPending: false,
  },
  lastOptions: undefined as { preferTactical?: boolean } | undefined,
}));

vi.mock("@/hooks/useSelectedPortfolio", () => ({
  useSelectedPortfolio: (_id: string | undefined, options?: { preferTactical?: boolean }) => {
    selection.lastOptions = options;
    return selection.current;
  },
}));

vi.mock("@/components/rebalancing/RecommendationCard", () => ({
  default: () => React.createElement("div", { "data-testid": "recommendation-card" }),
}));

// 청크 다운로드가 끝나지 않은 상태를 흉내 — 렌더 중 끝나지 않는 Promise로 suspend
const pending = new Promise<never>(() => {});
const tacticalBehavior = vi.hoisted(() => ({ suspend: true }));
vi.mock("@/components/rebalancing/TacticalAllocationTab", () => ({
  default: (props: { selectedPortfolioId?: string }) => {
    if (tacticalBehavior.suspend) throw pending;
    return React.createElement("div", { "data-testid": "tactical-tab" }, props.selectedPortfolioId);
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

  it("전술 모드는 전술 켜진 포트폴리오를 우선 고르게 요청하고 옵션에 '전술 켜짐'을 표시한다", async () => {
    tacticalBehavior.suspend = false;
    selection.current = {
      portfolios: [
        { id: "p1", name: "국내 배당" },
        { id: "p2", name: "미국 전술" },
      ],
      tacticalIds: ["p2"],
      selectedId: "p2",
      tacticalPending: false,
    };
    render(
      <MemoryRouter initialEntries={["/rebalancing?gmode=전술"]}>
        <Harness />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("tactical-tab")).toHaveTextContent("p2");
    expect(selection.lastOptions).toEqual({ preferTactical: true });
    expect(screen.getByRole("option", { name: "미국 전술 (전술 켜짐)" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "국내 배당" })).toBeInTheDocument();
    expect(screen.getByText(/시장 국면은 모든 포트폴리오에 같아요/)).toBeInTheDocument();
  });

  it("추천 모드는 상단 대상 포트폴리오 선택기를 그리지 않는다(적용 영역에서 고름)", async () => {
    render(
      <MemoryRouter initialEntries={["/rebalancing?gmode=추천"]}>
        <Harness />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("recommendation-card")).toBeInTheDocument();
    expect(selection.lastOptions).toEqual({ preferTactical: false });
    expect(screen.queryByText("대상 포트폴리오")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("전술 목록을 기다리는 동안은 전술 화면 대신 스켈레톤", () => {
    selection.current = { ...selection.current, tacticalPending: true };
    render(
      <MemoryRouter initialEntries={["/rebalancing?gmode=전술"]}>
        <Harness />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("tactical-tab")).not.toBeInTheDocument();
    expect(screen.getByRole("status", { name: "로딩 중" })).toBeInTheDocument();
  });
});
