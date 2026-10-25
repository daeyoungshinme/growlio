import { describe, it, expect, beforeEach } from "vitest";
import { hasStoredSession, readStoredSession, readValidStoredToken } from "@/lib/storedSession";

const KEY = "sb-testref-auth-token";

function store(session: unknown) {
  localStorage.setItem(KEY, typeof session === "string" ? session : JSON.stringify(session));
}

describe("storedSession", () => {
  beforeEach(() => localStorage.clear());

  it("저장 세션이 없으면 null", () => {
    expect(hasStoredSession()).toBe(false);
    expect(readStoredSession()).toBeNull();
    expect(readValidStoredToken()).toBeNull();
  });

  it("유효한 토큰은 그대로 반환한다", () => {
    const now = Date.now();
    store({ access_token: "tok", expires_at: Math.floor(now / 1000) + 3600, user: { id: "u1" } });
    expect(readStoredSession()).toMatchObject({ accessToken: "tok", userId: "u1" });
    expect(readValidStoredToken(now)).toBe("tok");
  });

  it("만료(여유 30초 포함)된 토큰은 null", () => {
    const now = Date.now();
    store({ access_token: "tok", expires_at: Math.floor(now / 1000) + 10, user: { id: "u1" } });
    expect(hasStoredSession()).toBe(true);
    expect(readValidStoredToken(now)).toBeNull();
  });

  it("형식을 해석할 수 없으면 null로 폴백한다", () => {
    store("not-json");
    expect(hasStoredSession()).toBe(true);
    expect(readStoredSession()).toBeNull();
    store({ token: "x" });
    expect(readStoredSession()).toBeNull();
  });
});
