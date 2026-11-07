import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/utils/platform", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/utils/platform")>()),
  isNativePlatform: () => false,
}));

import { useBiometric } from "@/hooks/useBiometric";

describe("useBiometric (plans/117 C4)", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("setEnabled가 같은 렌더 주기에 isEnabled를 바꾼다 — 토글 라벨이 바로 바뀌어야 한다", () => {
    const { result } = renderHook(() => useBiometric());
    expect(result.current.isEnabled).toBe(false);

    act(() => result.current.setEnabled(true));
    expect(result.current.isEnabled).toBe(true);
    expect(localStorage.getItem("growlio_biometric_enabled")).toBe("1");

    act(() => result.current.setEnabled(false));
    expect(result.current.isEnabled).toBe(false);
    expect(localStorage.getItem("growlio_biometric_enabled")).toBeNull();
  });
});
