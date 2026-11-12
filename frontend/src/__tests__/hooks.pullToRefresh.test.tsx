import { describe, it, expect, vi } from "vitest";
import { act, render, renderHook } from "@testing-library/react";
import { useRef, type ReactNode } from "react";
import { usePullToRefresh } from "@/hooks/usePullToRefresh";
import { useRegisterRefresh } from "@/hooks/useRegisterRefresh";
import { RefreshContext } from "@/components/layout/RefreshContext";

const haptic = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock("@/hooks/useHaptic", () => ({ triggerHaptic: haptic }));

function touch(el: HTMLElement, type: string, clientY?: number) {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperty(event, "touches", {
    value: clientY === undefined ? [] : [{ clientY }],
  });
  el.dispatchEvent(event);
  return event;
}

function Harness({ onRefresh, disabled }: { onRefresh: () => Promise<void>; disabled?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const { isPulling, isRefreshing } = usePullToRefresh({
    onRefresh,
    containerRef: ref,
    threshold: 60,
    disabled,
  });
  return (
    <div ref={ref} data-testid="scroller">
      {isPulling ? "pulling" : ""}
      {isRefreshing ? "refreshing" : ""}
    </div>
  );
}

describe("usePullToRefresh (plans/119 D5)", () => {
  it("임계값 이상 당겼다 놓으면 새로고침하고 햅틱을 한 번 울린다", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    const { getByTestId } = render(<Harness onRefresh={onRefresh} />);
    const el = getByTestId("scroller");

    touch(el, "touchstart", 0);
    let move!: Event;
    act(() => {
      move = touch(el, "touchmove", 200); // 200 * 0.5 = 100 ≥ 60
      touch(el, "touchmove", 220);
    });
    expect(move.defaultPrevented).toBe(true);
    expect(el.textContent).toContain("pulling");
    expect(haptic).toHaveBeenCalledTimes(1);

    await act(async () => {
      touch(el, "touchend");
    });
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(el.textContent).toBe("");
  });

  it("시스템이 제스처를 취소(touchcancel)하면 임계값을 넘었어도 새로고침하지 않는다 — plans/126 C3", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    const { getByTestId } = render(<Harness onRefresh={onRefresh} />);
    const el = getByTestId("scroller");

    touch(el, "touchstart", 0);
    act(() => {
      touch(el, "touchmove", 200);
    });
    await act(async () => {
      touch(el, "touchcancel");
    });
    expect(onRefresh).not.toHaveBeenCalled();
    expect(el.textContent).toBe("");
  });

  it("임계값 미만이면 새로고침하지 않는다", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    const { getByTestId } = render(<Harness onRefresh={onRefresh} />);
    const el = getByTestId("scroller");

    touch(el, "touchstart", 0);
    act(() => {
      touch(el, "touchmove", 40); // 20 < 60
    });
    await act(async () => {
      touch(el, "touchend");
    });
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it("위로 미는 동작·비활성 상태는 무시한다", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    const { getByTestId, rerender } = render(<Harness onRefresh={onRefresh} />);
    const el = getByTestId("scroller");

    touch(el, "touchstart", 100);
    const up = touch(el, "touchmove", 50);
    expect(up.defaultPrevented).toBe(false);

    rerender(<Harness onRefresh={onRefresh} disabled />);
    touch(el, "touchstart", 0);
    const blocked = touch(el, "touchmove", 300);
    expect(blocked.defaultPrevented).toBe(false);
    await act(async () => {
      touch(el, "touchend");
    });
    expect(onRefresh).not.toHaveBeenCalled();
  });
});

describe("useRegisterRefresh (plans/119 D5)", () => {
  it("마운트 시 콜백을 등록하고 언마운트 시 해제한다", () => {
    const registerRefresh = vi.fn();
    const fn = vi.fn().mockResolvedValue(undefined);
    const wrapper = ({ children }: { children: ReactNode }) => (
      <RefreshContext.Provider value={{ registerRefresh }}>{children}</RefreshContext.Provider>
    );

    const { unmount } = renderHook(() => useRegisterRefresh(fn), { wrapper });
    expect(registerRefresh).toHaveBeenLastCalledWith(fn);

    unmount();
    expect(registerRefresh).toHaveBeenLastCalledWith(null);
  });
});

describe("usePullToRefresh non-passive 리스너 범위 (plans/125 E2)", () => {
  it("스크롤된 상태에서 시작한 터치에는 touchmove를 가로채지 않는다", () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    const { getByTestId } = render(<Harness onRefresh={onRefresh} />);
    const el = getByTestId("scroller");
    Object.defineProperty(el, "scrollTop", { value: 120, configurable: true });
    const add = vi.spyOn(el, "addEventListener");

    touch(el, "touchstart", 0);
    const move = touch(el, "touchmove", 200);

    expect(move.defaultPrevented).toBe(false);
    expect(add.mock.calls.some(([type]) => type === "touchmove")).toBe(false);
  });

  it("맨 위에서 시작한 제스처가 끝나면 touchmove 리스너를 뗀다", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    const { getByTestId } = render(<Harness onRefresh={onRefresh} />);
    const el = getByTestId("scroller");
    const remove = vi.spyOn(el, "removeEventListener");

    touch(el, "touchstart", 0);
    await act(async () => {
      touch(el, "touchend");
    });

    expect(remove.mock.calls.some(([type]) => type === "touchmove")).toBe(true);
  });
});
