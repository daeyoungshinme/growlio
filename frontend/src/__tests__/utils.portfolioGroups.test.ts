import { describe, expect, it } from "vitest";
import type { IndexGroupSuggestion, PortfolioItem } from "@/api/portfolios";
import type { GoalRecommendationItem } from "@/api/rebalancing";
import type { RebalancingAnalysis, RebalancingItem } from "@/api/rebalancing";
import {
  applyIndexGroup,
  isLeveraged,
  memberLabel,
  outOfScopeAccounts,
  removeGroupMember,
  scopedMemberLabel,
  setGroupDomesticAlt,
  setGroupPrimary,
  ungroupItem,
} from "@/utils/portfolioGroups";
import {
  computeRecommendationDrift,
  toPortfolioItemsPreservingGroups,
} from "@/utils/recommendationDrift";
import {
  buyItemForAccount,
  calcTradeSummary,
  canBuyInAccount,
  domesticAltCandidates,
  flattenTradeItems,
  qtyInOriginalUnits,
} from "@/components/rebalancing/rebalancingTradeMath";

const m = (ticker: string, market: string, value_krw = 0) => ({
  ticker,
  market,
  name: ticker,
  value_krw,
});

const suggestion: IndexGroupSuggestion = {
  key: "US_SP500",
  label: "S&P 500",
  value_krw: 500_000,
  exposure_krw: 500_000,
  pct_of_stock: 50,
  primary: m("SPY", "NYSE", 400_000),
  domestic_alt: m("379800", "KOSPI", 100_000),
  members: [m("SPY", "NYSE", 400_000), m("379800", "KOSPI", 100_000), m("VOO", "NYSE", 0)],
  primary_candidates: [m("SPY", "NYSE"), m("VOO", "NYSE")],
  domestic_alt_candidates: [m("379800", "KOSPI"), m("360750", "KOSPI")],
};

const groupItem: PortfolioItem = {
  ticker: "SPY",
  market: "NYSE",
  name: "SPY",
  weight: 60,
  group: {
    key: "US_SP500",
    label: "S&P 500",
    members: [{ ticker: "VOO", market: "NYSE", name: "VOO" }],
    domestic_alt: { ticker: "379800", market: "KOSPI", name: "379800" },
  },
};

describe("applyIndexGroup", () => {
  it("merges same-index rows into one group row at the first row and sums weights", () => {
    const items: PortfolioItem[] = [
      { ticker: "QQQ", market: "NASDAQ", name: "QQQ", weight: 40 },
      { ticker: "SPY", market: "NYSE", name: "SPY", weight: 45 },
      { ticker: "379800", market: "KOSPI", name: "KODEX", weight: 15 },
    ];
    const result = applyIndexGroup(items, suggestion);
    expect(result.map((i) => i.ticker)).toEqual(["QQQ", "SPY"]);
    expect(result[1].weight).toBe(60);
    expect(result[1].group?.members.map((x) => x.ticker)).toEqual(["VOO"]);
    expect(result[1].group?.domestic_alt?.ticker).toBe("379800");
  });

  it("appends with weight 0 when no row matches", () => {
    const result = applyIndexGroup(
      [{ ticker: "QQQ", market: "NASDAQ", name: "", weight: 100 }],
      suggestion,
    );
    expect(result[1]).toMatchObject({ ticker: "SPY", weight: 0 });
  });
});

describe("group row edits", () => {
  it("setGroupPrimary keeps the old primary as a member", () => {
    const next = setGroupPrimary(groupItem, { ticker: "VOO", market: "NYSE", name: "VOO" });
    expect(next.ticker).toBe("VOO");
    expect(next.group?.members.map((x) => x.ticker)).toEqual(["SPY"]);
    expect(next.group?.domestic_alt?.ticker).toBe("379800");
  });

  it("domestic primary drops the domestic alt into members", () => {
    const next = setGroupPrimary(groupItem, { ticker: "379800", market: "KOSPI", name: "379800" });
    expect(next.group?.domestic_alt).toBeNull();
    expect(next.group?.members.map((x) => x.ticker).sort()).toEqual(["SPY", "VOO"]);
  });

  it("setGroupDomesticAlt moves the previous alt into members", () => {
    const next = setGroupDomesticAlt(groupItem, {
      ticker: "360750",
      market: "KOSPI",
      name: "TIGER",
    });
    expect(next.group?.domestic_alt?.ticker).toBe("360750");
    expect(next.group?.members.map((x) => x.ticker)).toEqual(["VOO", "379800"]);
  });

  it("removeGroupMember and ungroupItem", () => {
    expect(removeGroupMember(groupItem, { ticker: "VOO", market: "NYSE" }).group?.members).toEqual(
      [],
    );
    expect(ungroupItem(groupItem)).toEqual({
      ticker: "SPY",
      market: "NYSE",
      name: "SPY",
      weight: 60,
    });
  });
});

describe("recommendation folding", () => {
  const rec = (ticker: string, market: string, weight: number) =>
    ({ ticker, market, name: ticker, weight }) as GoalRecommendationItem;
  const current: PortfolioItem[] = [
    groupItem,
    { ticker: "QQQ", market: "NASDAQ", name: "QQQ", weight: 40 },
  ];

  it("does not count group members as new candidates", () => {
    const drift = computeRecommendationDrift(
      [rec("VOO", "NYSE", 30), rec("SPY", "NYSE", 30), rec("QQQ", "NASDAQ", 40)],
      current,
    );
    expect(drift).toEqual({ maxDeltaPct: 0, newCandidateCount: 0 });
  });

  it("keeps group metadata when applying a recommendation", () => {
    const items = toPortfolioItemsPreservingGroups(
      [rec("VOO", "NYSE", 50), rec("QQQ", "NASDAQ", 50)],
      current,
    );
    expect(items[0]).toMatchObject({ ticker: "SPY", weight: 50, group: groupItem.group });
    expect(items[1].group).toBeUndefined();
  });
});

describe("flattenTradeItems", () => {
  const base: RebalancingItem = {
    ticker: "SPY",
    name: "S&P 500",
    market: "NYSE",
    target_weight_pct: 50,
    current_weight_pct: 40,
    weight_diff_pct: 10,
    current_value_krw: 400_000,
    target_value_krw: 500_000,
    diff_krw: 100_000,
    shares_to_trade: null,
    current_price_krw: 100_000,
  };
  const group: RebalancingItem = {
    ...base,
    group_key: "US_SP500",
    members: [
      {
        ...base,
        group_role: "PRIMARY",
        current_value_krw: 300_000,
        target_value_krw: 400_000,
        shares_to_trade: 1,
      },
      {
        ...base,
        ticker: "VOO",
        group_role: "MEMBER",
        current_value_krw: 100_000,
        target_value_krw: 100_000,
        diff_krw: 0,
        shares_to_trade: 0,
      },
    ],
  };

  it("replaces group rows with traded members only", () => {
    expect(flattenTradeItems([group]).map((i) => i.ticker)).toEqual(["SPY"]);
  });

  it("trade summary counts group members, not the quantity-less group row", () => {
    expect(calcTradeSummary([group])).toEqual({ totalBuySummary: 100_000, totalSellSummary: 0 });
  });
});

describe("leveraged members", () => {
  it("applyIndexGroup keeps leverage on members", () => {
    const result = applyIndexGroup([], {
      ...suggestion,
      key: "US_NASDAQ100",
      primary: m("QQQ", "NASDAQ"),
      domestic_alt: null,
      members: [m("QQQ", "NASDAQ", 100), { ...m("QLD", "NASDAQ", 100), leverage: 2 }],
    });
    expect(result[0].group?.members).toEqual([
      { ticker: "QLD", market: "NASDAQ", name: "QLD", leverage: 2 },
    ]);
    expect(memberLabel(result[0].group!.members[0])).toBe("QLD ×2");
    expect(isLeveraged({ leverage: 1 })).toBe(false);
  });
});

describe("out-of-scope suggestion members", () => {
  it("maps members held only outside the analysed accounts", () => {
    const s = {
      ...suggestion,
      members: [
        { ...m("379800", "KOSPI"), in_scope: true },
        { ...m("QLD", "NASDAQ"), leverage: 2, in_scope: false, account_names: ["해외"] },
      ],
    };
    const outside = outOfScopeAccounts(s);
    expect([...outside.keys()]).toEqual(["QLD|NASDAQ"]);
    expect(scopedMemberLabel(s.members[1], outside.get("QLD|NASDAQ"))).toBe("QLD ×2(해외)");
    expect(scopedMemberLabel(s.members[0], outside.get("379800|KOSPI"))).toBe("379800");
  });
});

describe("buyItemForAccount (plans/79 E)", () => {
  const base: RebalancingItem = {
    ticker: "VOO",
    name: "VOO",
    market: "NYSE",
    target_weight_pct: 50,
    current_weight_pct: 40,
    weight_diff_pct: 10,
    current_value_krw: 400_000,
    target_value_krw: 1_000_000,
    diff_krw: 600_000,
    shares_to_trade: null,
    current_price_krw: 500_000,
  };
  const primary: RebalancingItem = {
    ...base,
    group_role: "PRIMARY",
    current_qty: 0,
    shares_to_trade: 1,
    target_value_krw: 600_000,
  };
  const alt: RebalancingItem = {
    ...base,
    ticker: "360750",
    name: "TIGER 미국S&P500",
    market: "KOSPI",
    group_role: "DOMESTIC_ALT",
    current_value_krw: 40_000,
    target_value_krw: 40_000,
    current_qty: 2,
    current_price_krw: 20_000,
    shares_to_trade: 0,
  };
  const group: RebalancingItem = {
    ...base,
    current_value_krw: 400_000,
    group_key: "US_SP500",
    members: [primary, alt],
  };

  it("ISA·연금 계좌는 해외 대표 대신 국내 대체를 그룹 차액만큼 산다", () => {
    for (const taxType of ["ISA", "PENSION_SAVINGS", "IRP"]) {
      const item = buyItemForAccount(primary, [group], taxType);
      // 차액 600,000 → 대체 목표 640,000 / 20,000 = 32주, 보유 2주 → 30주 매수
      expect(item).toMatchObject({
        ticker: "360750",
        market: "KOSPI",
        shares_to_trade: 30,
        target_qty: 32,
        substitute_for: "VOO",
      });
    }
  });

  it("일반 계좌·세제유형 미상이면 대표 종목 그대로", () => {
    expect(buyItemForAccount(primary, [group], "GENERAL")).toBe(primary);
    expect(buyItemForAccount(primary, [group], undefined)).toBe(primary);
  });

  it("대체 종목이 없거나 시세가 없으면 대표 종목 그대로", () => {
    const noAlt = { ...group, members: [primary] };
    expect(buyItemForAccount(primary, [noAlt], "ISA")).toBe(primary);
    const noPrice = { ...group, members: [primary, { ...alt, current_price_krw: null }] };
    expect(buyItemForAccount(primary, [noPrice], "ISA")).toBe(primary);
  });

  it("canBuyInAccount — 절세 계좌의 해외 종목은 국내 대체가 될 때만 (plans/80 A2)", () => {
    expect(canBuyInAccount(primary, [group], "ISA")).toBe(true);
    expect(canBuyInAccount(primary, [{ ...group, members: [primary] }], "IRP")).toBe(false);
    expect(canBuyInAccount(primary, [group], "GENERAL")).toBe(true);
    expect(canBuyInAccount(alt, [group], "PENSION_SAVINGS")).toBe(true);
  });

  it("qtyInOriginalUnits — 대체 행 수량을 대표 종목 주수로 환산", () => {
    const row = buyItemForAccount(primary, [group], "ISA");
    expect(qtyInOriginalUnits(row, primary, 25)).toBe(1); // 25 × 2만 ÷ 50만
    expect(qtyInOriginalUnits(primary, primary, 3)).toBe(3);
    expect(qtyInOriginalUnits({ ...row, current_price_krw: null }, primary, 25)).toBe(25);
  });

  it("대표 종목이 국내면 바꾸지 않는다", () => {
    const krPrimary = { ...primary, market: "KOSPI" };
    expect(buyItemForAccount(krPrimary, [{ ...group, members: [krPrimary, alt] }], "ISA")).toBe(
      krPrimary,
    );
  });

  it("국내 대체 후보 시세 조회 대상", () => {
    expect(
      domesticAltCandidates({ items: [group] } as unknown as RebalancingAnalysis).map(
        (i) => i.ticker,
      ),
    ).toEqual(["360750"]);
  });
});
