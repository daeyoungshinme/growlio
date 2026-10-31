import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render } from "@testing-library/react";
import { useRevealFocusedInput } from "@/hooks/useRevealFocusedInput";
import AuthLayout from "@/components/layout/AuthLayout";
import { SCROLL_INTO_VIEW_DELAY } from "@/constants/timers";

function Harness() {
  useRevealFocusedInput();
  return (
    <>
      <input aria-label="금액" />
      <button>버튼</button>
    </>
  );
}

describe("useRevealFocusedInput", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(window, "visualViewport", {
      configurable: true,
      value: { height: 400, offsetTop: 0 },
    });
  });
  afterEach(() => {
    vi.useRealTimers();
    Object.defineProperty(window, "visualViewport", { configurable: true, value: undefined });
  });

  function setup(bottom: number) {
    const { getByLabelText, getByText } = render(<Harness />);
    const input = getByLabelText("금액");
    input.getBoundingClientRect = () => ({ bottom }) as DOMRect;
    const scroll = vi.fn();
    input.scrollIntoView = scroll;
    return { input, button: getByText("버튼"), scroll };
  }

  it("키보드(뷰포트 하단) 아래에 가린 입력은 키보드가 올라온 뒤 가운데로 올린다", () => {
    const { input, scroll } = setup(600);
    input.focus();
    expect(scroll).not.toHaveBeenCalled();
    vi.advanceTimersByTime(SCROLL_INTO_VIEW_DELAY);
    expect(scroll).toHaveBeenCalledWith({ block: "center" });
  });

  it("이미 보이는 입력은 건드리지 않는다", () => {
    const visible = setup(300);
    visible.input.focus();
    vi.advanceTimersByTime(SCROLL_INTO_VIEW_DELAY);
    expect(visible.scroll).not.toHaveBeenCalled();
  });

  it("포커스가 떠나면 예약된 스크롤을 하지 않는다", () => {
    const { input, button, scroll } = setup(600);
    input.focus();
    button.focus();
    vi.advanceTimersByTime(SCROLL_INTO_VIEW_DELAY);
    expect(scroll).not.toHaveBeenCalled();
  });
});

describe("AuthLayout", () => {
  it("상태바·제스처바 safe-area와 dvh 높이를 잡고 내용은 가운데 둔다", () => {
    const { container, getByText } = render(
      <AuthLayout className="py-6">
        <p>로그인</p>
      </AuthLayout>,
    );
    const outer = container.firstElementChild as HTMLElement;
    expect(outer.className).toContain("min-h-dvh");
    expect(outer.className).toContain("pt-[env(safe-area-inset-top)]");
    expect(outer.className).toContain("pb-[env(safe-area-inset-bottom)]");
    expect(getByText("로그인").parentElement?.className).toContain("py-6");
  });
});
