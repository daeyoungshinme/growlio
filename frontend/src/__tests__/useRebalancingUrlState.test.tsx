import { describe, it, expect } from "vitest";
import type { ReactNode } from "react";
import { renderHook, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { useRebalancingUrlState } from "@/hooks/useRebalancingUrlState";

function renderAt(url: string) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[url]}>{children}</MemoryRouter>
  );
  return renderHook(() => useRebalancingUrlState(), { wrapper });
}

const q = encodeURIComponent;

describe("useRebalancingUrlState", () => {
  it("파라미터가 없으면 진단 탭·추천 모드", () => {
    const { result } = renderAt("/rebalancing");
    expect(result.current.tab).toBe("진단");
    expect(result.current.mode).toBe("추천");
    expect(result.current.portfolioId).toBeUndefined();
  });

  it("예전 rtab=전술 링크는 목표 조정 탭의 전술 모드로 연다", () => {
    const { result } = renderAt(`/rebalancing?rtab=${q("전술")}`);
    expect(result.current.tab).toBe("목표 조정");
    expect(result.current.mode).toBe("전술");
  });

  it("portfolioId를 읽는다", () => {
    const { result } = renderAt("/rebalancing?portfolioId=p-1");
    expect(result.current.portfolioId).toBe("p-1");
  });

  it("navigateTo는 탭을 바꾸고 다른 탭으로 가면 gmode를 지운다", () => {
    const { result } = renderAt(`/rebalancing?rtab=${q("목표 조정")}&gmode=${q("전술")}`);
    act(() => result.current.navigateTo({ tab: "이력" }));
    expect(result.current.tab).toBe("이력");
    expect(result.current.searchParams.get("gmode")).toBeNull();
  });

  it("clearParam은 해당 키만 지운다", () => {
    const { result } = renderAt("/rebalancing?portfolioId=p-1&openExecution=1");
    act(() => result.current.clearParam("openExecution"));
    expect(result.current.searchParams.get("openExecution")).toBeNull();
    expect(result.current.portfolioId).toBe("p-1");
  });
});
