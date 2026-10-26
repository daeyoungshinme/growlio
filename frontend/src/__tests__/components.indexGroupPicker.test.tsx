import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { IndexGroupSuggestion } from "@/api/portfolios";
import IndexGroupPicker from "@/components/portfolio-analysis/IndexGroupPicker";

const member = (ticker: string, market: string, name: string, extra = {}) => ({
  ticker,
  market,
  name,
  value_krw: 1_000_000,
  ...extra,
});

const nasdaq: IndexGroupSuggestion = {
  key: "US_NASDAQ100",
  label: "나스닥 100",
  value_krw: 4_000_000,
  exposure_krw: 5_000_000,
  pct_of_stock: 40,
  primary: member("QQQ", "NASDAQ", "Invesco QQQ Trust, Series 1"),
  domestic_alt: member("367380", "KOSPI", "KODEX 미국나스닥100TR"),
  members: [
    member("367380", "KOSPI", "KODEX 미국나스닥100TR", { in_scope: true }),
    member("QLD", "NYSE", "ProShares Ultra QQQ", {
      leverage: 2,
      in_scope: false,
      account_names: ["해외"],
    }),
    member("QQQ", "NASDAQ", "Invesco QQQ Trust, Series 1", {
      in_scope: false,
      account_names: ["해외"],
    }),
    member("438100", "KOSPI", "ACE 미국나스닥100채권혼합액티브", { in_scope: true }),
  ],
  primary_candidates: [],
  domestic_alt_candidates: [],
};

describe("IndexGroupPicker", () => {
  it("shows every member as a chip, including leveraged ones held outside the analysed accounts", () => {
    const onApply = vi.fn();
    render(
      <IndexGroupPicker
        data={{ groups: [nasdaq], profiles_complete: true }}
        isLoading={false}
        isError={false}
        appliedKeys={new Set()}
        onApply={onApply}
      />,
    );
    expect(screen.getByText("ProShares Ultra QQQ ×2(해외)")).toBeInTheDocument();
    expect(screen.getByText(/ACE 미국나스닥100채권혼합액티브/)).toBeInTheDocument();
    expect(screen.getByText("레버리지 종목은 배수만큼 노출로 합산해요.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "묶기" }));
    expect(onApply).toHaveBeenCalledWith(nasdaq);
  });
});
