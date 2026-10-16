import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { IndexExposure, PortfolioOverview } from "@/types";

vi.mock("@/api/portfolios", () => ({ fetchIndexExposure: vi.fn() }));

import AllocationCard from "@/components/portfolio/AllocationCard";
import { fetchIndexExposure } from "@/api/portfolios";

const EXPOSURE: IndexExposure = {
  total_stock_krw: 10_000_000,
  total_etf_krw: 8_000_000,
  profiles_complete: true,
  region_exposure: { domestic_krw: 2_000_000, overseas_krw: 7_000_000, unknown_krw: 1_000_000 },
  groups: [
    {
      key: "US_SP500",
      label: "S&P 500",
      kind: "INDEX",
      value_krw: 6_000_000,
      pct_of_stock: 60,
      pct_of_etf: 75,
      has_hedged: true,
      domestic_krw: 3_000_000,
      overseas_krw: 3_000_000,
      members: [
        {
          ticker: "SPY",
          name: "SPDR S&P 500 ETF Trust",
          market: "AMEX",
          listing: "OVERSEAS",
          value_krw: 3_000_000,
          hedged: false,
          pct_of_stock: 30,
          region: "OVERSEAS",
        },
        {
          ticker: "360750",
          name: "TIGER 미국S&P500",
          market: "KOSPI",
          listing: "DOMESTIC",
          value_krw: 3_000_000,
          hedged: false,
          pct_of_stock: 30,
          region: "OVERSEAS",
        },
      ],
    },
    {
      key: "LEVERAGED",
      label: "레버리지·인버스",
      kind: "LEVERAGED",
      value_krw: 2_000_000,
      pct_of_stock: 20,
      pct_of_etf: 25,
      has_hedged: false,
      domestic_krw: 0,
      overseas_krw: 2_000_000,
      members: [],
    },
    {
      key: "STOCK",
      label: "개별주",
      kind: "STOCK",
      value_krw: 2_000_000,
      pct_of_stock: 20,
      pct_of_etf: null,
      has_hedged: false,
      domestic_krw: 2_000_000,
      overseas_krw: 0,
      members: [],
    },
  ],
};

const OVERVIEW = {
  total_assets_krw: 12_000_000,
  total_stock_krw: 10_000_000,
  total_non_stock_krw: 2_000_000,
  total_invested_krw: 9_000_000,
  unrealized_pnl_krw: 1_000_000,
  stock_return_pct: 11.1,
  domestic_stock_krw: 6_000_000,
  foreign_stock_krw: 4_000_000,
  asset_type_allocation: [],
  stock_allocation: [
    {
      ticker: "SPY",
      name: "SPDR S&P 500 ETF Trust",
      market: "AMEX",
      value_krw: 3_000_000,
      pct: 30,
    },
    { ticker: "360750", name: "TIGER 미국S&P500", market: "KOSPI", value_krw: 3_000_000, pct: 30 },
    { ticker: "005930", name: "삼성전자", market: "KOSPI", value_krw: 2_000_000, pct: 20 },
    { ticker: "ETC", name: "기타 3종목", market: null, value_krw: 2_000_000, pct: 20 },
  ],
  all_positions: [],
  accounts: [],
} satisfies PortfolioOverview;

function renderCard({
  exposure = EXPOSURE,
  overview = OVERVIEW,
  accountId = null,
}: {
  exposure?: IndexExposure;
  overview?: PortfolioOverview;
  accountId?: string | null;
} = {}) {
  vi.mocked(fetchIndexExposure).mockResolvedValue(exposure);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AllocationCard overview={overview} accountId={accountId} />
    </QueryClientProvider>,
  );
}

const clickView = (name: string) =>
  fireEvent.click(
    within(screen.getByRole("group", { name: "비중 보기" })).getByRole("button", { name }),
  );

describe("AllocationCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  describe("국내/해외", () => {
    it("기본은 실제 투자지역 기준이며 판별 불가를 따로 보여준다", async () => {
      renderCard();
      // 스택 바 라벨 + 범례에 같은 값이 나온다
      expect(await screen.findAllByText("70.0%")).toHaveLength(2); // 해외 7/10
      expect(screen.getAllByText("20.0%")).toHaveLength(2); // 국내
      expect(screen.getByText("판별 불가")).toBeInTheDocument();
      expect(screen.getByText(/국내상장 미국 ETF/)).toBeInTheDocument();
    });

    it("상장시장 기준으로 바꾸면 overview 금액을 쓴다", async () => {
      renderCard();
      fireEvent.click(screen.getByRole("button", { name: "상장시장" }));
      expect(screen.getAllByText("60.0%")).toHaveLength(2);
      expect(screen.getAllByText("40.0%")).toHaveLength(2);
      expect(screen.queryByText("판별 불가")).not.toBeInTheDocument();
    });

    it("지수 조회 실패 시 다시 시도 버튼을 보여준다", async () => {
      vi.mocked(fetchIndexExposure).mockRejectedValue(new Error("boom"));
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={qc}>
          <AllocationCard overview={OVERVIEW} />
        </QueryClientProvider>,
      );
      expect(await screen.findByText("비중 정보를 불러오지 못했어요")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
      expect(fetchIndexExposure).toHaveBeenCalledTimes(2);
    });
  });

  describe("종목", () => {
    it("순위·상장 배지·집중도 요약을 보여주고 지수 조회는 하지 않는다", () => {
      localStorage.setItem("growlio:portfolio:allocationView", "stock");
      renderCard();
      expect(screen.getByText("최대 종목")).toBeInTheDocument();
      expect(screen.getByText("상위 3종목 합계")).toBeInTheDocument();
      expect(screen.getByText("80.0%")).toBeInTheDocument();
      expect(screen.getAllByText("국내상장")).toHaveLength(2);
      expect(screen.getAllByText("해외상장")).toHaveLength(1);
      expect(screen.getByText("기타 3종목")).toBeInTheDocument();
      expect(screen.getByText("아래 보유 종목 목록에서 확인")).toBeInTheDocument();
      expect(fetchIndexExposure).not.toHaveBeenCalled();
    });

    it("상위 5종목만 그리고 6위 이하는 백엔드 기타와 합쳐 한 행으로 보여준다", () => {
      localStorage.setItem("growlio:portfolio:allocationView", "stock");
      const ranked = Array.from({ length: 7 }, (_, i) => ({
        ticker: `T${i + 1}`,
        name: `종목${i + 1}`,
        market: "KOSPI",
        value_krw: 1_000_000,
        pct: 10,
      }));
      renderCard({
        overview: {
          ...OVERVIEW,
          stock_allocation: [
            ...ranked,
            { ticker: "ETC", name: "기타 4종목", market: null, value_krw: 3_000_000, pct: 30 },
          ],
        },
      });
      expect(screen.getByText("종목5")).toBeInTheDocument();
      expect(screen.queryByText("종목6")).not.toBeInTheDocument();
      expect(screen.getByText("상위 5종목 합계")).toBeInTheDocument();
      // 6·7위(20%) + 기타 4종목(30%) = 6종목 50%
      expect(screen.getByText("기타 6종목")).toBeInTheDocument();
      expect(screen.getAllByText("50.0%").length).toBeGreaterThan(0);
    });

    it("전체 비중순 보기 버튼은 콜백이 있을 때만 보이고 누르면 호출된다", () => {
      localStorage.setItem("growlio:portfolio:allocationView", "stock");
      const onShowAllStocks = vi.fn();
      vi.mocked(fetchIndexExposure).mockResolvedValue(EXPOSURE);
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <AllocationCard overview={OVERVIEW} onShowAllStocks={onShowAllStocks} />
        </QueryClientProvider>,
      );
      fireEvent.click(screen.getByRole("button", { name: "보유 종목 전체 비중순 보기" }));
      expect(onShowAllStocks).toHaveBeenCalledTimes(1);
      unmount();
      renderCard();
      expect(
        screen.queryByRole("button", { name: "보유 종목 전체 비중순 보기" }),
      ).not.toBeInTheDocument();
    });

    it("보유 종목이 없으면 빈 상태 문구", () => {
      localStorage.setItem("growlio:portfolio:allocationView", "stock");
      renderCard({ overview: { ...OVERVIEW, stock_allocation: [] } });
      expect(screen.getByText("보유 종목이 없어요.")).toBeInTheDocument();
    });
  });

  describe("지수", () => {
    it("지수 그룹을 주식 전체 기준 비중과 상장시장 분할로 보여준다", async () => {
      renderCard();
      clickView("지수");
      expect(await screen.findByText("S&P 500")).toBeInTheDocument();
      expect(screen.getByText("60.0%")).toBeInTheDocument();
      expect(screen.getByText("(H) 포함")).toBeInTheDocument();
      expect(screen.getByText("국내상장 50% · 해외상장 50%")).toBeInTheDocument();
      expect(screen.getByText("개별주")).toBeInTheDocument();
    });

    it("ETF만 기준으로 바꾸면 개별주를 숨기고 ETF 대비 비중을 쓴다", async () => {
      renderCard();
      clickView("지수");
      await screen.findByText("S&P 500");
      fireEvent.click(screen.getByRole("button", { name: "ETF만" }));
      expect(screen.queryByText("개별주")).not.toBeInTheDocument();
      expect(screen.getByText("75.0%")).toBeInTheDocument();
    });

    it("그룹을 누르면 구성 종목을 펼친다", async () => {
      renderCard();
      clickView("지수");
      const row = (await screen.findByText("S&P 500")).closest("li")!;
      expect(within(row).queryByText("SPY")).not.toBeInTheDocument();
      fireEvent.click(within(row).getByRole("button"));
      expect(within(row).getByText("SPY")).toBeInTheDocument();
      expect(within(row).getByText("TIGER 미국S&P500")).toBeInTheDocument();
    });

    it("구성 종목이 없는 그룹은 펼침 버튼이 없다", async () => {
      renderCard();
      clickView("지수");
      const row = (await screen.findByText("개별주")).closest("li")!;
      expect(within(row).queryByRole("button")).not.toBeInTheDocument();
    });

    it("프로필 조회가 불완전하면 안내를 표시한다", async () => {
      renderCard({ exposure: { ...EXPOSURE, profiles_complete: false } });
      clickView("지수");
      expect(await screen.findByText(/분류가 정확하지 않을 수 있어요/)).toBeInTheDocument();
    });

    it("ETF가 없으면 빈 상태 문구", async () => {
      renderCard({ exposure: { ...EXPOSURE, total_etf_krw: 0, groups: [EXPOSURE.groups[2]] } });
      clickView("지수");
      expect(await screen.findByText("보유 중인 ETF가 없어요.")).toBeInTheDocument();
    });

    it("선택한 계좌 ID로 조회한다", async () => {
      renderCard({ accountId: "acc-1" });
      clickView("지수");
      await screen.findByText("S&P 500");
      expect(fetchIndexExposure).toHaveBeenCalledWith("acc-1");
    });
  });

  it("선택한 탭을 기억한다", () => {
    renderCard();
    clickView("종목");
    expect(localStorage.getItem("growlio:portfolio:allocationView")).toBe("stock");
  });

  it("접으면 최대 종목과 해외상장 비중 요약을 보여준다", () => {
    localStorage.setItem("growlio:portfolio:allocationOpen", "false");
    renderCard();
    expect(
      screen.getByText("최대 종목 SPDR S&P 500 ETF Trust 30.0% · 해외상장 40%"),
    ).toBeInTheDocument();
  });

  describe("기본 펼침 상태", () => {
    // jsdom에는 matchMedia가 없다 — 테스트마다 정의하고 지운다
    const mockViewport = (desktop: boolean) =>
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        writable: true,
        value: (query: string) => ({ matches: desktop, media: query }) as MediaQueryList,
      });

    afterEach(() => {
      delete (window as { matchMedia?: unknown }).matchMedia;
    });

    it("모바일 폭에서는 기본 접힘이고 지수 조회도 하지 않는다", () => {
      mockViewport(false);
      renderCard();
      expect(screen.getByRole("button", { name: /비중 분석/ })).toHaveAttribute(
        "aria-expanded",
        "false",
      );
      expect(fetchIndexExposure).not.toHaveBeenCalled();
    });

    it("데스크톱 폭에서는 기본 펼침", () => {
      mockViewport(true);
      renderCard();
      expect(screen.getByRole("button", { name: /비중 분석/ })).toHaveAttribute(
        "aria-expanded",
        "true",
      );
    });

    it("사용자가 펼쳐 둔 상태는 모바일에서도 유지된다", () => {
      mockViewport(false);
      localStorage.setItem("growlio:portfolio:allocationOpen", "true");
      renderCard();
      expect(screen.getByRole("button", { name: /비중 분석/ })).toHaveAttribute(
        "aria-expanded",
        "true",
      );
    });
  });
});
