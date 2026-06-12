import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import Tooltip from "@/components/common/Tooltip";
import { SideBadge, StatusBadge } from "@/components/rebalancing/RebalancingBadges";
import { isNativePlatform, getApiBaseUrl } from "@/utils/platform";
import { toast } from "@/utils/toast";

vi.mock("@/hooks/useHaptic", () => ({
  triggerHaptic: vi.fn().mockResolvedValue(undefined),
}));

describe("Tooltip", () => {
  it("콘텐츠와 children을 렌더링한다", () => {
    renderWithProviders(
      <Tooltip content="도움말 텍스트">
        <button>버튼</button>
      </Tooltip>
    );
    expect(screen.getByText("버튼")).toBeInTheDocument();
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    expect(screen.getByText("도움말 텍스트")).toBeInTheDocument();
  });

  it("기본 position이 top이다", () => {
    renderWithProviders(
      <Tooltip content="툴팁">
        <span>요소</span>
      </Tooltip>
    );
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip.className).toContain("bottom-full");
  });

  it("position=bottom이면 아래 위치 클래스가 적용된다", () => {
    renderWithProviders(
      <Tooltip content="툴팁" position="bottom">
        <span>요소</span>
      </Tooltip>
    );
    expect(screen.getByRole("tooltip").className).toContain("top-full");
  });
});

describe("RebalancingBadges", () => {
  it("SideBadge isBuy=true이면 '매수'를 표시한다", () => {
    renderWithProviders(<SideBadge isBuy={true} />);
    expect(screen.getByText("매수")).toBeInTheDocument();
  });

  it("SideBadge isBuy=false이면 '매도'를 표시한다", () => {
    renderWithProviders(<SideBadge isBuy={false} />);
    expect(screen.getByText("매도")).toBeInTheDocument();
  });

  it("StatusBadge SUCCESS이면 '성공'을 표시한다", () => {
    renderWithProviders(<StatusBadge status="SUCCESS" />);
    expect(screen.getByText("성공")).toBeInTheDocument();
  });

  it("StatusBadge FAILED이면 '실패'를 표시한다", () => {
    renderWithProviders(<StatusBadge status="FAILED" />);
    expect(screen.getByText("실패")).toBeInTheDocument();
  });

  it("StatusBadge SKIPPED이면 '건너뜀'을 표시한다", () => {
    renderWithProviders(<StatusBadge status="SKIPPED" />);
    expect(screen.getByText("건너뜀")).toBeInTheDocument();
  });
});

describe("platform utils", () => {
  it("isNativePlatform()이 일반 브라우저에서 false를 반환한다", () => {
    expect(isNativePlatform()).toBe(false);
  });

  it("getApiBaseUrl()이 웹 환경에서 빈 문자열을 반환한다", () => {
    expect(getApiBaseUrl()).toBe("");
  });

  it("isNativePlatform()이 Capacitor 환경에서 true를 반환한다", () => {
    const win = window as { Capacitor?: { isNativePlatform?: () => boolean } };
    win.Capacitor = { isNativePlatform: () => true };
    expect(isNativePlatform()).toBe(true);
    delete win.Capacitor;
  });
});

describe("toast util", () => {
  let listener: ((e: CustomEvent) => void) | null = null;

  beforeEach(() => {
    listener = null;
  });

  afterEach(() => {
    if (listener) {
      window.removeEventListener("growlio:toast", listener as EventListener);
    }
  });

  it("toast()가 growlio:toast 이벤트를 발행한다", () => {
    const spy = vi.fn();
    listener = spy;
    window.addEventListener("growlio:toast", spy as EventListener);
    toast("테스트 메시지", "success");
    expect(spy).toHaveBeenCalled();
    const detail = spy.mock.calls[0][0].detail;
    expect(detail.message).toBe("테스트 메시지");
    expect(detail.type).toBe("success");
  });

  it("기본 type은 error이다", () => {
    const spy = vi.fn();
    listener = spy;
    window.addEventListener("growlio:toast", spy as EventListener);
    toast("에러 메시지");
    const detail = spy.mock.calls[0][0].detail;
    expect(detail.type).toBe("error");
  });
});
