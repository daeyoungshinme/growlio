import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders } from "@/test/renderWithProviders";

// Mock API calls
vi.mock("@/api/rebalancing", () => ({
  fetchRebalancingHistory: vi.fn().mockResolvedValue([]),
  fetchRebalancingExecutionDetail: vi.fn().mockResolvedValue(null),
}));

vi.mock("@/api/marketSignals", () => ({
  fetchMarketSignal: vi.fn().mockResolvedValue(null),
}));

vi.mock("@/hooks/useRebalancingExecution", () => ({
  isOverseasMarket: vi.fn((market: string) => ["NASDAQ", "NYSE", "AMEX", "TSX"].includes(market)),
}));

import { SideBadge, StatusBadge } from "@/components/rebalancing/RebalancingBadges";
import MarketSignalLevelBadge from "@/components/rebalancing/MarketSignalLevelBadge";
import MarketSignalBanner from "@/components/rebalancing/MarketSignalBanner";
import { PriceCell } from "@/components/rebalancing/RebalancingPriceCell";
import {
  DiffCell,
  WeightDiffBadge,
  WeightBar,
  SharesCell,
  DividendDiffCell,
  Return10yCell,
  CagrCard,
} from "@/components/rebalancing/RebalancingCells";
import RebalancingHistoryTab from "@/components/rebalancing/RebalancingHistoryTab";
import type { MarketSignalResponse } from "@/api/marketSignals";
import type { RebalancingItem } from "@/api/rebalancing";

// ------- SideBadge -------
describe("SideBadge", () => {
  it("renders buy badge", () => {
    render(<SideBadge isBuy={true} />);
    expect(screen.getByText("매수")).toBeDefined();
  });

  it("renders sell badge", () => {
    render(<SideBadge isBuy={false} />);
    expect(screen.getByText("매도")).toBeDefined();
  });
});

// ------- StatusBadge -------
describe("StatusBadge", () => {
  it("renders success status", () => {
    render(<StatusBadge status="SUCCESS" />);
    expect(screen.getByText("성공")).toBeDefined();
  });

  it("renders failed status", () => {
    render(<StatusBadge status="FAILED" />);
    expect(screen.getByText("실패")).toBeDefined();
  });

  it("renders skipped status", () => {
    render(<StatusBadge status="SKIPPED" />);
    expect(screen.getByText("건너뜀")).toBeDefined();
  });
});

// ------- MarketSignalLevelBadge -------
describe("MarketSignalLevelBadge", () => {
  it("renders GREEN level", () => {
    render(<MarketSignalLevelBadge level="GREEN" />);
    expect(screen.getByText("안전")).toBeDefined();
  });

  it("renders YELLOW level", () => {
    render(<MarketSignalLevelBadge level="YELLOW" />);
    expect(screen.getByText("주의")).toBeDefined();
  });

  it("renders RED level", () => {
    render(<MarketSignalLevelBadge level="RED" />);
    expect(screen.getByText("위험")).toBeDefined();
  });

  it("renders sm size", () => {
    const { container } = render(<MarketSignalLevelBadge level="GREEN" size="sm" />);
    expect(container.firstChild).toBeDefined();
  });
});

// ------- MarketSignalBanner -------
const mockSignal: MarketSignalResponse = {
  composite_level: "YELLOW",
  composite_score: 50,
  composite_score_max: 20,
  data_freshness: "LIVE",
  fear_greed_contrarian_buy: false,
  fear_greed_extreme_greed: false,
  computed_at: "2024-01-15T00:00:00Z",
  signals: {
    vix: { value: 20.5, level: "MEDIUM", date: "2024-01-15", sub_score: 1 },
    yield_curve: { value: -0.5, state: "INVERTED", date: "2024-01-15", sub_score: 1 },
    fear_greed: {
      value: 45,
      label: "공포",
      label_en: "Fear",
      classification: "FEAR",
      sub_score: 1,
    },
    high_yield_spread: { value: 3.5, level: "NORMAL", date: "2024-01-15", sub_score: 0 },
    dollar_index: { value: 104.0, ma20: 103.0, deviation_pct: 0.97, level: "NORMAL", date: "2024-01-15", sub_score: 0 },
    rate_cut_expectation: { value: -0.5, dgs2: 4.5, fedfunds: 5.0, level: "MILD_CUT_EXPECTED", date: "2024-01-15", sub_score: 1 },
  },
};

describe("MarketSignalBanner", () => {
  const renderBanner = (signal = mockSignal) =>
    renderWithProviders(<MemoryRouter><MarketSignalBanner signal={signal} /></MemoryRouter>);

  it("renders signal banner with label", () => {
    renderBanner();
    expect(screen.getByText("시장 위험 신호")).toBeDefined();
  });

  it("shows short implication text for YELLOW", () => {
    renderBanner();
    expect(screen.getByText(/분할 집행 권장/)).toBeDefined();
  });

  it("shows detail link to market page", () => {
    renderBanner();
    const link = screen.getByLabelText("시장 신호 상세 보기");
    expect(link).toBeDefined();
  });

  it("shows stale data freshness inline", () => {
    renderBanner({ ...mockSignal, data_freshness: "STALE" as const });
    expect(screen.getByText(/데이터 조회 불가/)).toBeDefined();
  });

  it("shows partial data freshness inline", () => {
    renderBanner({ ...mockSignal, data_freshness: "PARTIAL" as const });
    expect(screen.getByText(/일부 데이터 없음/)).toBeDefined();
  });
});

// ------- PriceCell -------
describe("PriceCell", () => {
  it("renders loading state", () => {
    render(
      <PriceCell
        ticker="AAPL"
        market="NASDAQ"
        priceState="loading"
        livePricesKrw={{}}
        livePricesUsd={{}}
      />,
    );
    expect(screen.getByText("조회 중")).toBeDefined();
  });

  it("renders Korean price", () => {
    render(
      <PriceCell
        ticker="005930"
        market="KOSPI"
        priceState="loaded"
        livePricesKrw={{ "005930": 75000 }}
        livePricesUsd={{}}
      />,
    );
    expect(screen.getByText(/75,000/)).toBeDefined();
  });

  it("renders USD + KRW for overseas", () => {
    render(
      <PriceCell
        ticker="AAPL"
        market="NASDAQ"
        priceState="loaded"
        livePricesKrw={{ AAPL: 170000 }}
        livePricesUsd={{ AAPL: 125.5 }}
      />,
    );
    expect(screen.getByText(/125\.50/)).toBeDefined();
  });

  it("renders dash when no price", () => {
    render(
      <PriceCell
        ticker="AAPL"
        market="NASDAQ"
        priceState="loaded"
        livePricesKrw={{}}
        livePricesUsd={{}}
      />,
    );
    expect(screen.getByText("—")).toBeDefined();
  });
});

// ------- RebalancingCells -------
describe("DiffCell", () => {
  it("renders positive diff", () => {
    const { container } = render(<DiffCell diff={500000} />);
    // fmtKrw formats to Korean units (만원 etc)
    expect(container.textContent).toContain("+");
  });

  it("renders negative diff", () => {
    const { container } = render(<DiffCell diff={-300000} />);
    expect(container.textContent?.length).toBeGreaterThan(0);
  });

  it("renders zero diff", () => {
    render(<DiffCell diff={0} />);
    expect(screen.getByText("-")).toBeDefined();
  });
});

describe("WeightDiffBadge", () => {
  it("renders positive weight diff", () => {
    render(<WeightDiffBadge diff={5.5} />);
    expect(screen.getByText(/▲.*5\.5%/)).toBeDefined();
  });

  it("renders negative weight diff", () => {
    render(<WeightDiffBadge diff={-3.2} />);
    expect(screen.getByText(/▼.*3\.2%/)).toBeDefined();
  });

  it("renders zero diff", () => {
    render(<WeightDiffBadge diff={0.05} />);
    expect(screen.getByText("±0%")).toBeDefined();
  });
});

describe("WeightBar", () => {
  it("renders weight bar", () => {
    const { container } = render(<WeightBar current={30} target={40} />);
    expect(container.querySelector(".rounded-full")).toBeDefined();
  });
});

const mockRebalancingItem: RebalancingItem = {
  ticker: "AAPL",
  name: "Apple Inc.",
  market: "NASDAQ",
  current_weight_pct: 15,
  target_weight_pct: 20,
  weight_diff_pct: 5,
  current_value_krw: 1500000,
  target_value_krw: 2000000,
  diff_krw: 500000,
  shares_to_trade: 3,
  current_price_krw: 170000,
  annual_dividend_current_krw: 50000,
  annual_dividend_target_krw: 65000,
  annual_dividend_diff_krw: 15000,
  cagr_10y_pct: 12.5,
  return_10y_pct: 224.0,
  actual_years_10y: 10,
};

describe("SharesCell", () => {
  it("renders positive shares to trade", () => {
    render(<SharesCell item={mockRebalancingItem} />);
    expect(screen.getByText("+3주")).toBeDefined();
  });

  it("renders zero shares", () => {
    render(<SharesCell item={{ ...mockRebalancingItem, shares_to_trade: 0 }} />);
    expect(screen.getByText("0")).toBeDefined();
  });

  it("renders null shares", () => {
    render(<SharesCell item={{ ...mockRebalancingItem, shares_to_trade: null }} />);
    expect(screen.getByText("-")).toBeDefined();
  });
});

describe("DividendDiffCell", () => {
  it("renders positive diff", () => {
    render(<DividendDiffCell diff={15000} />);
    expect(screen.getByText(/\+/)).toBeDefined();
  });

  it("renders zero diff", () => {
    render(<DividendDiffCell diff={0} />);
    expect(screen.getByText("-")).toBeDefined();
  });
});

describe("Return10yCell", () => {
  it("renders return data", () => {
    render(<Return10yCell item={mockRebalancingItem} />);
    expect(screen.getByText(/12\.5%/)).toBeDefined();
  });

  it("renders null cagr", () => {
    render(
      <Return10yCell item={{ ...mockRebalancingItem, cagr_10y_pct: null, return_10y_pct: null }} />,
    );
    expect(screen.getByText("—")).toBeDefined();
  });
});

describe("CagrCard", () => {
  it("renders cagr card", () => {
    render(<CagrCard label="포트폴리오" cagr={8.5} />);
    expect(screen.getByText("포트폴리오")).toBeDefined();
    expect(screen.getByText(/8\.5%/)).toBeDefined();
  });

  it("renders null cagr as nothing", () => {
    const { container } = render(<CagrCard label="포트폴리오" cagr={null} />);
    expect(container.firstChild).toBeNull();
  });
});

// ------- RebalancingHistoryTab -------
describe("RebalancingHistoryTab", () => {
  it("renders without crash", () => {
    renderWithProviders(<RebalancingHistoryTab />);
    // Shows loading or empty state
    expect(document.body).toBeDefined();
  });
});
