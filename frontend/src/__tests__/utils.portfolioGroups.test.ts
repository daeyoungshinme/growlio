import { describe, expect, it } from "vitest";
import type { IndexGroupSuggestion, PortfolioItem } from "@/api/portfolios";
import type { GoalRecommendationItem } from "@/api/rebalancing";
import type { RebalancingItem } from "@/api/rebalancing";
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
import { calcTradeSummary, flattenTradeItems } from "@/components/rebalancing/rebalancingTradeMath";

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
