import { describe, it, expect, vi } from "vitest";
import { renderHook, act, render, screen } from "@testing-library/react";
import { createCredentialVerify } from "@/hooks/createCredentialVerify";
import CredentialVerifyButton from "@/components/assets/CredentialVerifyButton";

describe("createCredentialVerify", () => {
  it("성공 시 idle → loading → ok 로 전이한다", async () => {
    const apiCall = vi.fn().mockResolvedValue({ valid: true });
    const useVerify = createCredentialVerify(apiCall);
    const { result } = renderHook(() => useVerify());

    expect(result.current.verifyState).toBe("idle");

    await act(async () => {
      await result.current.verify("key", "secret");
    });

    expect(apiCall).toHaveBeenCalledWith("key", "secret");
    expect(result.current.verifyState).toBe("ok");
    expect(result.current.verifyError).toBe("");
  });

  it("실패 시 error 상태 + API 에러 메시지를 노출한다", async () => {
    const apiCall = vi.fn().mockRejectedValue({
      response: { data: { detail: "자격증명이 잘못되었습니다" } },
    });
    const useVerify = createCredentialVerify(apiCall);
    const { result } = renderHook(() => useVerify());

    await act(async () => {
      await result.current.verify();
    });

    expect(result.current.verifyState).toBe("error");
    expect(result.current.verifyError).toBe("자격증명이 잘못되었습니다");
  });

  it("에러 메시지를 못 뽑으면 기본 문구로 폴백한다", async () => {
    const useVerify = createCredentialVerify(vi.fn().mockRejectedValue({ weird: true }));
    const { result } = renderHook(() => useVerify());

    await act(async () => {
      await result.current.verify();
    });

    expect(result.current.verifyState).toBe("error");
    expect(result.current.verifyError).toBe("자격증명 확인 실패");
  });

  it("reset 은 상태를 idle 로 되돌린다 (재검증 시나리오)", async () => {
    const useVerify = createCredentialVerify(vi.fn().mockResolvedValue({}));
    const { result } = renderHook(() => useVerify());

    await act(async () => {
      await result.current.verify();
    });
    expect(result.current.verifyState).toBe("ok");

    act(() => result.current.reset());
    expect(result.current.verifyState).toBe("idle");
  });
});

describe("CredentialVerifyButton", () => {
  const baseProps = {
    show: true,
    disabled: false,
    verifyState: "idle" as const,
    verifyError: "",
    onVerify: vi.fn(),
  };

  it("show=false 면 아무것도 렌더하지 않는다", () => {
    const { container } = render(<CredentialVerifyButton {...baseProps} show={false} />);
    expect(container.firstChild).toBeNull();
  });

  it("클릭 시 onVerify 를 호출한다", () => {
    const onVerify = vi.fn();
    render(<CredentialVerifyButton {...baseProps} onVerify={onVerify} />);
    screen.getByRole("button", { name: "자격증명 확인" }).click();
    expect(onVerify).toHaveBeenCalledOnce();
  });

  it("loading 이면 버튼이 disabled + '확인 중...' 을 표시한다", () => {
    render(<CredentialVerifyButton {...baseProps} verifyState="loading" />);
    expect(screen.getByRole("button", { name: "확인 중..." })).toHaveProperty("disabled", true);
  });

  it("disabled prop 이면 버튼이 비활성화된다", () => {
    render(<CredentialVerifyButton {...baseProps} disabled />);
    expect(screen.getByRole("button", { name: "자격증명 확인" })).toHaveProperty("disabled", true);
  });

  it("ok / error 상태의 결과 메시지를 렌더한다", () => {
    const { rerender } = render(<CredentialVerifyButton {...baseProps} verifyState="ok" />);
    expect(screen.getByText("자격증명 확인됨")).toBeDefined();

    rerender(
      <CredentialVerifyButton {...baseProps} verifyState="error" verifyError="키가 틀렸습니다" />,
    );
    expect(screen.getByText("키가 틀렸습니다")).toBeDefined();
  });
});
