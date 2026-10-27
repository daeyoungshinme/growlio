import { describe, expect, it } from "vitest";
import { resolveSelectedPortfolioId } from "@/hooks/useSelectedPortfolio";

describe("resolveSelectedPortfolioId (plans/64 S2)", () => {
  const ids = ["p1", "p2", "p3"];

  it("URL에서 고른 포트폴리오가 목록에 있으면 그대로", () => {
    expect(resolveSelectedPortfolioId("p3", ids, ["p2"])).toBe("p3");
  });

  it("URL 값이 없거나 목록에 없으면 첫 기준 포트폴리오", () => {
    expect(resolveSelectedPortfolioId(undefined, ids, ["p2"])).toBe("p2");
    expect(resolveSelectedPortfolioId("deleted", ids, ["p2"])).toBe("p2");
  });

  it("우선 후보는 앞에서부터, 목록에 없는 후보는 건너뛴다 (plans/81 전술 켜짐 → 기준 순)", () => {
    expect(resolveSelectedPortfolioId(undefined, ids, ["p3", "p2"])).toBe("p3");
    expect(resolveSelectedPortfolioId(undefined, ids, ["deleted", "p2"])).toBe("p2");
    expect(resolveSelectedPortfolioId("p1", ids, ["p3", "p2"])).toBe("p1");
  });

  it("기준 포트폴리오도 없으면 첫 포트폴리오, 포트폴리오가 없으면 undefined", () => {
    expect(resolveSelectedPortfolioId(undefined, ids, [])).toBe("p1");
    expect(resolveSelectedPortfolioId(undefined, [], [])).toBeUndefined();
  });
});
