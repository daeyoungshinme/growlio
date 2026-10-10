import { describe, it, expect } from "vitest";
import { legacyAssetsTaxRedirect, legacyHistorySegment } from "@/utils/legacyTabRedirect";

describe("legacyAssetsTaxRedirect", () => {
  it("세금 탭이 아니면 리다이렉트하지 않는다", () => {
    expect(legacyAssetsTaxRedirect(new URLSearchParams("tab=투자현황&portfolioTab=배당"))).toBe(
      null,
    );
  });

  it("세금 서브탭·계좌 필터를 계획 › 절세 파라미터로 옮긴다", () => {
    const url = legacyAssetsTaxRedirect(
      new URLSearchParams("tab=투자현황&portfolioTab=세금&taxTab=세금 추정&account=a1"),
    );
    const parsed = new URL(url!, "http://x");
    expect(parsed.pathname).toBe("/invest-plan");
    expect(parsed.searchParams.get("tab")).toBe("절세");
    expect(parsed.searchParams.get("taxTab")).toBe("세금 추정");
    expect(parsed.searchParams.get("taxAccount")).toBe("a1");
  });

  it("서브탭·계좌가 없으면 절세 탭만 지정한다", () => {
    expect(legacyAssetsTaxRedirect(new URLSearchParams("portfolioTab=세금"))).toBe(
      `/invest-plan?${new URLSearchParams({ tab: "절세" }).toString()}`,
    );
  });
});

describe("legacyHistorySegment (계좌관리 내역 통합)", () => {
  it("옛 입출금·배당/기간별 매수 탭을 내역 세그먼트로 매핑한다", () => {
    expect(legacyHistorySegment("입출금·배당")).toBe("현금 흐름");
    expect(legacyHistorySegment("기간별 매수")).toBe("매수 내역");
    expect(legacyHistorySegment("증권계좌")).toBeNull();
    expect(legacyHistorySegment(null)).toBeNull();
  });
});
