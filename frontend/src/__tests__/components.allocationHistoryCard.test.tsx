import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

const chartModuleLoaded = vi.fn();
vi.mock("@/components/dashboard/AllocationHistoryChart", () => {
  chartModuleLoaded();
  return {
    default: ({ onCollapse }: { onCollapse: () => void }) => (
      <button onClick={onCollapse}>chart-body</button>
    ),
  };
});

import AllocationHistoryCard from "@/components/dashboard/AllocationHistoryCard";

describe("AllocationHistoryCard", () => {
  beforeEach(() => {
    localStorage.clear();
    chartModuleLoaded.mockClear();
    Object.defineProperty(window, "innerWidth", { value: 375, configurable: true });
  });

  it("모바일 기본 접힘에서는 차트 청크를 로드하지 않고, 펼치면 로드한다", async () => {
    render(<AllocationHistoryCard />);

    expect(screen.getByText("자산 추이")).toBeDefined();
    expect(chartModuleLoaded).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(await screen.findByText("chart-body")).toBeDefined();
    expect(chartModuleLoaded).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText("chart-body"));
    expect(screen.getByRole("button", { expanded: false })).toBeDefined();
  });
});
