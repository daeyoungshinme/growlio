import { describe, expect, it } from "vitest";
import { parseRebalancingTab, rebalancingUrl } from "@/utils/rebalancingUrl";

const parse = (query: string) => parseRebalancingTab(new URLSearchParams(query));

describe("parseRebalancingTab", () => {
  it("현재 탭 이름을 그대로 읽는다", () => {
    expect(parse("rtab=포트폴리오")).toEqual({ tab: "포트폴리오", mode: "추천" });
    expect(parse("rtab=목표 조정&gmode=전술")).toEqual({ tab: "목표 조정", mode: "전술" });
  });

  it("예전 탭 값 추천·전술은 목표 조정 탭의 해당 모드로 매핑한다(발송된 링크 호환)", () => {
    expect(parse("rtab=추천")).toEqual({ tab: "목표 조정", mode: "추천" });
    expect(parse("rtab=전술")).toEqual({ tab: "목표 조정", mode: "전술" });
  });

  it("알 수 없거나 없는 값은 진단, 모드는 추천", () => {
    expect(parse("")).toEqual({ tab: "진단", mode: "추천" });
    expect(parse("rtab=없는탭&gmode=이상")).toEqual({ tab: "진단", mode: "추천" });
  });
});

describe("rebalancingUrl", () => {
  const read = (url: string) => decodeURIComponent(url);

  it("인자가 없으면 기본 경로", () => {
    expect(rebalancingUrl()).toBe("/rebalancing");
  });

  it("탭·포트폴리오·딥링크 파라미터를 조립한다", () => {
    expect(read(rebalancingUrl({ tab: "포트폴리오", portfolioId: "p1", openAlert: "dca" }))).toBe(
      "/rebalancing?rtab=포트폴리오&portfolioId=p1&openAlert=dca",
    );
    expect(read(rebalancingUrl({ tab: "목표 조정", mode: "추천", openRecOptions: true }))).toBe(
      "/rebalancing?rtab=목표 조정&gmode=추천&openRecOptions=1",
    );
  });

  it("공백은 + 가 아니라 %20으로 인코딩한다", () => {
    expect(rebalancingUrl({ tab: "목표 조정" })).not.toContain("+");
  });

  it("만든 링크를 다시 읽으면 같은 탭·모드가 나온다", () => {
    const url = rebalancingUrl({ tab: "목표 조정", mode: "전술" });
    expect(parse(url.split("?")[1]!)).toEqual({ tab: "목표 조정", mode: "전술" });
  });
});
