import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("@/hooks/useHaptic", () => ({
  triggerHaptic: vi.fn().mockResolvedValue(undefined),
  useHaptic: vi.fn(),
}));

import { triggerHaptic } from "@/hooks/useHaptic";
import { toast } from "@/utils/toast";

describe("toast", () => {
  let dispatchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    dispatchSpy = vi.spyOn(window, "dispatchEvent");
  });

  afterEach(() => {
    dispatchSpy.mockRestore();
  });

  it("success 타입이면 growlio:toast 이벤트를 발행하고 haptic을 호출한다", () => {
    toast("저장되었습니다", "success");

    expect(triggerHaptic).toHaveBeenCalledWith("success");
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "growlio:toast",
        detail: expect.objectContaining({ message: "저장되었습니다", type: "success" }),
      }),
    );
  });

  it("error 타입이면 haptic('error')를 호출하고 이벤트를 발행한다", () => {
    toast("에러 발생", "error");

    expect(triggerHaptic).toHaveBeenCalledWith("error");
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        detail: expect.objectContaining({ message: "에러 발생", type: "error" }),
      }),
    );
  });

  it("info 타입이면 haptic을 호출하지 않는다", () => {
    toast("정보 메시지", "info");

    expect(triggerHaptic).not.toHaveBeenCalled();
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        detail: expect.objectContaining({ type: "info" }),
      }),
    );
  });

  it("type 생략 시 기본값은 error다", () => {
    toast("기본 오류");

    expect(triggerHaptic).toHaveBeenCalledWith("error");
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        detail: expect.objectContaining({ type: "error" }),
      }),
    );
  });

  it("이벤트 detail에 숫자 id가 포함된다", () => {
    toast("test");

    const call = dispatchSpy.mock.calls[0][0] as CustomEvent;
    expect(typeof call.detail.id).toBe("number");
  });

  it("연속 호출 시 id가 단조 증가한다", () => {
    toast("a");
    toast("b");

    const first = (dispatchSpy.mock.calls[0][0] as CustomEvent).detail.id as number;
    const second = (dispatchSpy.mock.calls[1][0] as CustomEvent).detail.id as number;
    expect(second).toBeGreaterThan(first);
  });
});
