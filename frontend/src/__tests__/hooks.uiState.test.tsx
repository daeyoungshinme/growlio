import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, render, act, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useCollapsible } from "@/hooks/useCollapsible";
import { useModalBehavior } from "@/hooks/useModalBehavior";
import { useSettingsToggle } from "@/hooks/useSettingsToggle";
import { useChallengeMutations } from "@/hooks/useChallengeMutations";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { toast } from "@/utils/toast";

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

vi.mock("@/api/settings", () => ({
  fetchSettings: vi.fn().mockResolvedValue({ monthly_report_enabled: true }),
}));

vi.mock("@/api/challenges", () => ({
  createChallenge: vi.fn().mockResolvedValue({ id: "c-1" }),
  updateChallenge: vi.fn().mockResolvedValue({ id: "c-1" }),
  deleteChallenge: vi.fn().mockRejectedValue(new Error("삭제 실패")),
}));

function wrapperWith(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

function newQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

describe("useCollapsible", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("toggle·setIsOpen 참조가 렌더 사이에 고정된다 (effect 의존성에 넣어도 재실행되지 않음)", () => {
    const { result, rerender } = renderHook(() => useCollapsible(false, "k"));
    const [, toggle1, set1] = result.current;
    act(() => toggle1());
    rerender();
    const [isOpen, toggle2, set2] = result.current;
    expect(isOpen).toBe(true);
    expect(toggle2).toBe(toggle1);
    expect(set2).toBe(set1);
  });

  it("저장된 값을 초기값보다 우선하고, 변경을 저장한다", () => {
    localStorage.setItem("k", "true");
    const { result } = renderHook(() => useCollapsible(false, "k"));
    expect(result.current[0]).toBe(true);
    act(() => result.current[2](false));
    expect(localStorage.getItem("k")).toBe("false");
  });

  it("저장소 접근이 막혀도 렌더가 깨지지 않고 기본값으로 동작한다", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    const { result } = renderHook(() => useCollapsible(true, "k"));
    expect(result.current[0]).toBe(true);
    act(() => result.current[1]());
    expect(result.current[0]).toBe(false);
  });
});

function Modal({ onClose, label }: { onClose: () => void; label: string }) {
  const { dialogRef, overlayRef } = useModalBehavior(onClose);
  return (
    <div ref={overlayRef}>
      <div ref={dialogRef}>
        <button>{label}-첫번째</button>
        <button>{label}-마지막</button>
      </div>
    </div>
  );
}

describe("useModalBehavior", () => {
  it("겹친 모달은 마지막 모달이 닫힐 때만 body 스크롤 잠금을 원래 값으로 돌린다", () => {
    document.body.style.overflow = "auto";
    const a = render(<Modal onClose={() => {}} label="a" />);
    const b = render(<Modal onClose={() => {}} label="b" />);
    expect(document.body.style.overflow).toBe("hidden");
    b.unmount();
    expect(document.body.style.overflow).toBe("hidden");
    a.unmount();
    expect(document.body.style.overflow).toBe("auto");
  });

  it("열리면 첫 요소에 포커스, Tab은 마지막→첫, Shift+Tab은 첫→마지막으로 순환한다", () => {
    const { getByText, unmount } = render(<Modal onClose={() => {}} label="m" />);
    const first = getByText("m-첫번째");
    const last = getByText("m-마지막");
    expect(document.activeElement).toBe(first);

    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(first);

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
    unmount();
  });

  it("닫히면 열기 전 포커스로 돌아간다", () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    const { unmount } = render(<Modal onClose={() => {}} label="r" />);
    expect(document.activeElement).not.toBe(opener);
    unmount();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});

describe("useSettingsToggle", () => {
  beforeEach(() => vi.mocked(toast).mockClear());

  it("settings 값을 읽고, 저장 성공 시 무효화 콜백을 호출한다", async () => {
    const qc = newQueryClient();
    const invalidate = vi.fn();
    const mutationFn = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(
      () =>
        useSettingsToggle({
          field: "monthly_report_enabled",
          defaultValue: false,
          mutationFn,
          invalidate,
        }),
      { wrapper: wrapperWith(qc) },
    );
    expect(result.current.enabled).toBe(false); // 로드 전 기본값
    await waitFor(() => expect(result.current.enabled).toBe(true));

    act(() => result.current.toggle(false));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith(qc));
    expect(mutationFn.mock.calls[0]![0]).toBe(false);
  });

  it("저장 실패 시 에러 토스트, 무효화하지 않는다", async () => {
    const invalidate = vi.fn();
    const { result } = renderHook(
      () =>
        useSettingsToggle({
          field: "monthly_report_enabled",
          defaultValue: false,
          mutationFn: vi.fn().mockRejectedValue(new Error("x")),
          invalidate,
        }),
      { wrapper: wrapperWith(newQueryClient()) },
    );
    act(() => result.current.toggle(true));
    await waitFor(() => expect(toast).toHaveBeenCalledWith(expect.any(String), "error"));
    expect(invalidate).not.toHaveBeenCalled();
  });
});

describe("useChallengeMutations", () => {
  beforeEach(() => vi.mocked(toast).mockClear());

  it("생성 성공 시 성공 토스트와 챌린지 데이터 무효화", async () => {
    const qc = newQueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useChallengeMutations(), { wrapper: wrapperWith(qc) });
    await act(() => result.current.create.mutateAsync({} as never));
    expect(toast).toHaveBeenCalledWith("챌린지가 생성되었습니다", "success");
    expect(spy).toHaveBeenCalledWith({ queryKey: QUERY_KEYS.challenges });
  });

  it("삭제 실패 시 에러 토스트만, 무효화 없음", async () => {
    const qc = newQueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useChallengeMutations(), { wrapper: wrapperWith(qc) });
    act(() => result.current.remove.mutate("c-1"));
    await waitFor(() => expect(toast).toHaveBeenCalledWith(expect.any(String), "error"));
    expect(spy).not.toHaveBeenCalled();
  });
});
