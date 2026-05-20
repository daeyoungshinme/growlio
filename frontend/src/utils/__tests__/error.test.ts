import { describe, it, expect } from "vitest";
import { extractErrorMessage } from "../error";

describe("extractErrorMessage", () => {
  it("axios 응답 detail 추출", () => {
    const axiosErr = { response: { data: { detail: "인증이 필요합니다" } } };
    expect(extractErrorMessage(axiosErr)).toBe("인증이 필요합니다");
  });

  it("Error 인스턴스 메시지 추출", () => {
    expect(extractErrorMessage(new Error("네트워크 오류"))).toBe("네트워크 오류");
  });

  it("문자열은 그대로 반환", () => {
    expect(extractErrorMessage("커스텀 에러")).toBe("커스텀 에러");
  });

  it("null/undefined → fallback 반환", () => {
    expect(extractErrorMessage(null)).toBe("오류가 발생했습니다");
    expect(extractErrorMessage(undefined)).toBe("오류가 발생했습니다");
  });

  it("커스텀 fallback 사용", () => {
    expect(extractErrorMessage(null, "동기화에 실패했습니다")).toBe("동기화에 실패했습니다");
  });

  it("axios detail이 없으면 fallback 반환", () => {
    const axiosErrNoDetail = { response: { data: {} } };
    expect(extractErrorMessage(axiosErrNoDetail, "기본 오류")).toBe("기본 오류");
  });
});
