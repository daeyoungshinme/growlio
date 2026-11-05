import { describe, expect, it } from "vitest";
import {
  summarizeAllocationHistory,
  summarizeAmounts,
  summarizeBacktestAnnual,
  summarizeBacktestCumulative,
  summarizeBacktestDrawdown,
  summarizeProjection,
  summarizeSavings,
  summarizeWeights,
} from "@/utils/chartSummary";

describe("summarizeWeights", () => {
  it("큰 비중 순으로 나열하고 나머지는 개수로 알린다", () => {
    const items = [
      { name: "A", pct: 10 },
      { name: "B", pct: 50 },
      { name: "C", pct: 40 },
    ];
    expect(summarizeWeights("비중", items, 2)).toBe("비중: B 50.0%, C 40.0% 외 1개");
    expect(summarizeWeights("비중", items)).toBe("비중: B 50.0%, C 40.0%, A 10.0%");
  });

  it("항목이 없으면 없다고 말한다", () => {
    expect(summarizeWeights("비중", [])).toBe("비중: 데이터 없음");
  });
});

describe("summarizeAmounts", () => {
  it("합계·최고·최저를 말한다", () => {
    const points = [
      { name: "1월", amount: 10_000 },
      { name: "2월", amount: 50_000 },
      { name: "3월", amount: 0 },
    ];
    expect(summarizeAmounts("배당", points)).toBe("배당: 합계 6만원, 최고 2월 5만원, 최저 3월 0원");
  });

  it("전부 0이거나 비어 있으면 최고·최저를 말하지 않는다", () => {
    expect(summarizeAmounts("배당", [{ name: "1월", amount: 0 }])).toBe("배당: 금액 없음");
    expect(summarizeAmounts("배당", [])).toBe("배당: 데이터 없음");
  });
});

describe("summarizeAllocationHistory", () => {
  it("최신 달(첫 원소)의 총액과 상위 3개를 말한다", () => {
    const label = summarizeAllocationHistory([
      {
        month: "2026-11",
        allocations: [
          { label: "주식", amount_krw: 30_000_000 },
          { label: "현금", amount_krw: 10_000_000 },
          { label: "예금", amount_krw: 5_000_000 },
          { label: "기타", amount_krw: 1_000_000 },
        ],
      },
      { month: "2026-10", allocations: [{ label: "주식", amount_krw: 1 }] },
    ]);
    expect(label).toBe(
      "자산 구성 추이 차트: 2개월, 2026-11 총 4,600만원 (주식 3,000만원, 현금 1,000만원, 예금 500만원)",
    );
  });

  it("데이터가 없으면 없다고 말한다", () => {
    expect(summarizeAllocationHistory([])).toBe("자산 구성 추이 차트: 데이터 없음");
  });
});

describe("summarizeProjection", () => {
  it("마지막 실제 자산과 차트 끝 전망을 말한다", () => {
    expect(
      summarizeProjection([
        { month: "2026-10", actual_krw: 10_000_000, projected_krw: 9_000_000 },
        { month: "2026-11", actual_krw: null, projected_krw: 11_000_000 },
        { month: "2026-12", actual_krw: null, projected_krw: 12_000_000 },
      ]),
    ).toBe("자산 전망 차트: 2026-10 실제 자산 1,000만원, 2026-12 전망 1,200만원");
  });

  it("실제 자산이 없으면 전망만 말한다", () => {
    expect(
      summarizeProjection([{ month: "2026-12", actual_krw: null, projected_krw: 12_000_000 }]),
    ).toBe("자산 전망 차트: 실제 자산 없음, 2026-12 전망 1,200만원");
    expect(summarizeProjection([])).toBe("자산 전망 차트: 데이터 없음");
  });
});

describe("summarizeSavings", () => {
  it("기간·평가액·원금을 말한다", () => {
    expect(summarizeSavings(30, 300_000_000, 100_000_000)).toBe(
      "복리 시뮬레이션 차트: 30년 뒤 3.00억원, 투자 원금 1.00억원",
    );
  });
});

describe("백테스트 요약", () => {
  it("누적은 기준 100에서 마지막 유효값까지의 수익률이다", () => {
    expect(
      summarizeBacktestCumulative([
        { name: "전략", values: [null, 100, 150.5, null] },
        { name: "지수", values: [100, 90] },
        { name: "빈 시리즈", values: [null] },
      ]),
    ).toBe("누적 수익 차트: 전략 +50.5%, 지수 -10.0%");
  });

  it("연도별은 전략별 최고·최저 연도를 말한다", () => {
    expect(
      summarizeBacktestAnnual(
        [{ name: "전략" }, { name: "빈 시리즈" }],
        [
          { year: "2024", 전략: 10, "빈 시리즈": null },
          { year: "2025", 전략: -5, "빈 시리즈": null },
        ],
      ),
    ).toBe("연도별 수익률 차트: 전략 최고 2024년 +10.0%, 최저 2025년 -5.0%");
  });

  it("낙폭은 전략별 최솟값이다", () => {
    expect(summarizeBacktestDrawdown([{ name: "전략", values: [0, -12.3, null, -4] }])).toBe(
      "최대 낙폭 차트: 전략 -12.3%",
    );
    expect(summarizeBacktestDrawdown([])).toBe("최대 낙폭 차트: 데이터 없음");
  });
});
