import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { shouldPersistQuery } from "@/constants/queryConfig";

function queryWith(key: string, state: "success" | "error") {
  const client = new QueryClient();
  const cache = client.getQueryCache();
  const query = cache.build<unknown, Error, unknown, readonly unknown[]>(client, {
    queryKey: [key],
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
});
