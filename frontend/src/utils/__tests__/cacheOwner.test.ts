import { beforeEach, describe, expect, it } from "vitest";
import { PERSIST_CACHE_KEY } from "@/constants/queryConfig";
import { claimCacheOwner } from "@/utils/cacheOwner";

describe("claimCacheOwner (plans/61 B3)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("같은 사용자가 다시 로그인하면 캐시를 유지한다", () => {
    claimCacheOwner("user-a");
    localStorage.setItem(PERSIST_CACHE_KEY, "{}");
    expect(claimCacheOwner("user-a")).toBe(false);
    expect(localStorage.getItem(PERSIST_CACHE_KEY)).toBe("{}");
  });

  it("다른 사용자가 로그인하면 persist 캐시를 지우고 true", () => {
    claimCacheOwner("user-a");
    localStorage.setItem(PERSIST_CACHE_KEY, "{}");
    expect(claimCacheOwner("user-b")).toBe(true);
    expect(localStorage.getItem(PERSIST_CACHE_KEY)).toBeNull();
    expect(claimCacheOwner("user-b")).toBe(false);
  });

  it("소유자 기록 없이 남은 캐시는 누구 것인지 모르므로 지운다", () => {
    localStorage.setItem(PERSIST_CACHE_KEY, "{}");
    expect(claimCacheOwner("user-a")).toBe(true);
    expect(localStorage.getItem(PERSIST_CACHE_KEY)).toBeNull();
  });

  it("첫 로그인(캐시·기록 없음)은 변경으로 보지 않는다", () => {
    expect(claimCacheOwner("user-a")).toBe(false);
  });
});
