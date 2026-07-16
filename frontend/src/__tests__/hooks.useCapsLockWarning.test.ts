import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import type { KeyboardEvent } from "react";
import { useCapsLockWarning } from "@/hooks/useCapsLockWarning";

function keyEvent(capsLockOn: boolean) {
  return {
    getModifierState: () => capsLockOn,
  } as unknown as KeyboardEvent<HTMLInputElement>;
}

describe("useCapsLockWarning", () => {
  it("초기 상태는 isCapsLockOn이 false다", () => {
    const { result } = renderHook(() => useCapsLockWarning());
    expect(result.current.isCapsLockOn).toBe(false);
  });

  it("CapsLock이 켜진 상태로 키 이벤트가 발생하면 isCapsLockOn이 true가 된다", () => {
    const { result } = renderHook(() => useCapsLockWarning());
    act(() => {
      result.current.handleKeyEvent(keyEvent(true));
    });
    expect(result.current.isCapsLockOn).toBe(true);
  });

  it("CapsLock이 꺼지면 isCapsLockOn이 다시 false가 된다", () => {
    const { result } = renderHook(() => useCapsLockWarning());
    act(() => {
      result.current.handleKeyEvent(keyEvent(true));
    });
    expect(result.current.isCapsLockOn).toBe(true);
    act(() => {
      result.current.handleKeyEvent(keyEvent(false));
    });
    expect(result.current.isCapsLockOn).toBe(false);
  });
});
