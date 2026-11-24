import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { persistQueryPrefixes, shouldPersistQuery } from "@/constants/queryConfig";

function queryWith(key: string | readonly string[], state: "success" | "error") {
  const client = new QueryClient();
  const cache = client.getQueryCache();
  const query = cache.build<unknown, Error, unknown, readonly unknown[]>(client, {
    queryKey: typeof key === "string" ? [key] : key,
  });
  if (state === "success") query.setData({ ok: true });
  else query.setState({ status: "error", error: new Error("boom"), data: undefined });
  return query;
}

describe("shouldPersistQuery (plans/61 B4)", () => {
  it("persist 대상의 성공한 쿼리만 저장한다", () => {
    expect(shouldPersistQuery(queryWith("dashboard", "success"))).toBe(true);
  });

  it("persist 대상이라도 실패한 쿼리는 저장하지 않는다", () => {
    expect(shouldPersistQuery(queryWith("dashboard", "error"))).toBe(false);
  });

  it("persist 대상이 아닌 키는 저장하지 않는다", () => {
    expect(shouldPersistQuery(queryWith("settings", "success"))).toBe(false);
  });

  it("홈 첫 화면 카드 쿼리도 저장한다 (plans/125 C2)", () => {
    for (const key of [
      "action-items",
      "challenges",
      "portfolios",
      "market-signal",
      "exchange-rate",
    ]) {
      expect(shouldPersistQuery(queryWith(key, "success"))).toBe(true);
    }
  });

  it("목표 추천은 전체(overall)만 저장한다", () => {
    expect(shouldPersistQuery(queryWith(["goal-recommendation", "overall"], "success"))).toBe(true);
    expect(shouldPersistQuery(queryWith(["goal-recommendation", "by-horizon"], "success"))).toBe(
      false,
    );
  });

  it("overview는 홈 lite와 전체 계좌(all)만 — 계좌별 전체 응답은 저장하지 않는다 (plans/151 A10)", () => {
    expect(shouldPersistQuery(queryWith(["portfolio-overview", "lite"], "success"))).toBe(true);
    expect(shouldPersistQuery(queryWith(["portfolio-overview", "all"], "success"))).toBe(true);
    expect(shouldPersistQuery(queryWith(["portfolio-overview", "acc-123"], "success"))).toBe(false);
  });

  it("gcTime 프리픽스가 저장 범위와 같다", () => {
    const prefixes = persistQueryPrefixes();
    expect(prefixes).toContainEqual(["portfolio-overview", "lite"]);
    expect(prefixes).toContainEqual(["goal-recommendation", "overall"]);
    expect(prefixes).not.toContainEqual(["portfolio-overview"]);
    expect(prefixes).toContainEqual(["dashboard"]);
  });
});
