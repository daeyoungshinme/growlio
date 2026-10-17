import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getLocalStorageOrUndefined,
  sessionGet,
  sessionSet,
  storageGet,
  storageSet,
} from "../safeStorage";

/** 사이트 데이터 차단(Chrome) 시 storage 객체 접근 자체가 SecurityError를 던지는 상황을 재현 */
function blockStorage(name: "localStorage" | "sessionStorage") {
  return vi.spyOn(window, name, "get").mockImplementation(() => {
    throw new DOMException("blocked", "SecurityError");
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  localStorage.clear();
});

describe("safeStorage", () => {
  it("정상 환경에서는 그대로 읽고 쓴다", () => {
    sessionSet("k", "1");
    storageSet("k", "2");
    expect(sessionGet("k")).toBe("1");
    expect(storageGet("k")).toBe("2");
    expect(getLocalStorageOrUndefined()).toBe(window.localStorage);
  });

  it("sessionStorage가 막히면 읽기는 null, 쓰기는 조용히 무시한다", () => {
    blockStorage("sessionStorage");
    expect(sessionGet("k")).toBeNull();
    expect(() => sessionSet("k", "1")).not.toThrow();
  });

  it("localStorage가 막히면 persister용 storage는 undefined(캐시 없이 부팅)", () => {
    blockStorage("localStorage");
    expect(getLocalStorageOrUndefined()).toBeUndefined();
    expect(storageGet("k")).toBeNull();
  });
});
