import { describe, it, expect, afterEach, vi } from "vitest";
import { isNativePlatform, getApiBaseUrl } from "@/utils/platform";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("isNativePlatform", () => {
  it("Capacitor가 없으면 false를 반환한다", () => {
    expect(isNativePlatform()).toBe(false);
  });

  it("Capacitor.isNativePlatform()이 true이면 true를 반환한다", () => {
    vi.stubGlobal("Capacitor", { isNativePlatform: () => true });
    expect(isNativePlatform()).toBe(true);
  });

  it("Capacitor.isNativePlatform()이 예외를 던지면 false를 반환한다", () => {
    vi.stubGlobal("Capacitor", {
      isNativePlatform: () => {
        throw new Error("Capacitor error");
      },
    });
    expect(isNativePlatform()).toBe(false);
  });
});

describe("getApiBaseUrl", () => {
  it("웹 환경에서 빈 문자열을 반환한다", () => {
    expect(getApiBaseUrl()).toBe("");
  });

  it("네이티브 환경에서 VITE_API_DOMAIN 기반 https URL을 반환한다", () => {
    vi.stubGlobal("Capacitor", { isNativePlatform: () => true });
    vi.stubEnv("VITE_API_DOMAIN", "api.example.com");
    expect(getApiBaseUrl()).toBe("https://api.example.com");
  });

  it("네이티브 환경에서 VITE_API_DOMAIN 미설정 시 localhost:8000을 기본값으로 사용한다", () => {
    vi.stubGlobal("Capacitor", { isNativePlatform: () => true });
    expect(getApiBaseUrl()).toBe("https://localhost:8000");
  });
});
