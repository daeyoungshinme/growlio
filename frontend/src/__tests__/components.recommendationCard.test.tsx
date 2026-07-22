import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders as renderWithProvidersBase } from "@/test/renderWithProviders";
import type {
  GoalRecommendation,
  HorizonGoalRecommendation,
  HorizonRecommendationResponse,
} from "@/api/rebalancing";
import type { SettingsData } from "@/api/settings";
import type { Portfolio } from "@/api/portfolios";
import type { AssetAccount } from "@/api/assets";

const fetchOverallGoalRecommendation = vi.fn();
const fetchHorizonGoalRecommendations = vi.fn();
const fetchSettings = vi.fn();
const updateGoalCandidateTickers = vi.fn();
const updateGoalRecommendationOptions = vi.fn();
const fetchPortfolios = vi.fn();
const updatePortfolio = vi.fn();
const fetchAccounts = vi.fn();
const useStockSearchMock = vi.fn();
const toastMock = vi.fn();

vi.mock("@/api/rebalancing", () => ({
  fetchOverallGoalRecommendation: (...args: unknown[]) => fetchOverallGoalRecommendation(...args),
  fetchHorizonGoalRecommendations: (...args: unknown[]) => fetchHorizonGoalRecommendations(...args),
  CASH_EQUIVALENT_TICKER: "CASH_EQUIVALENT",
}));

vi.mock("@/api/settings", () => ({
  fetchSettings: (...args: unknown[]) => fetchSettings(...args),
  updateGoalCandidateTickers: (...args: unknown[]) => updateGoalCandidateTickers(...args),
  updateGoalRecommendationOptions: (...args: unknown[]) => updateGoalRecommendationOptions(...args),
}));

vi.mock("@/api/portfolios", () => ({
  fetchPortfolios: (...args: unknown[]) => fetchPortfolios(...args),
  updatePortfolio: (...args: unknown[]) => updatePortfolio(...args),
}));

vi.mock("@/api/assets", async () => {
  const actual = await vi.importActual<typeof import("@/api/assets")>("@/api/assets");
  return {
    ...actual,
    fetchAccounts: (...args: unknown[]) => fetchAccounts(...args),
  };
});

vi.mock("@/hooks/useStockSearch", () => ({
  useStockSearch: (...args: unknown[]) => useStockSearchMock(...args),
}));

vi.mock("@/utils/toast", () => ({ toast: (...args: unknown[]) => toastMock(...args) }));

import RecommendationCard from "@/components/rebalancing/RecommendationCard";

// RecommendationCard가 목표 미설정 안내에 <Link>(react-router-dom)를 렌더링하므로 Router 컨텍스트가 필요하다.
function renderWithProviders(ui: ReactNode) {
  return renderWithProvidersBase(<MemoryRouter>{ui}</MemoryRouter>);
}

function makePortfolio(overrides: Partial<Portfolio> = {}): Portfolio {
  return {
    id: "p1",
    name: "메인 포트폴리오",
    items: [{ ticker: "AAPL", name: "Apple", market: "NASDAQ", weight: 100 }],
    base_type: "STOCK_ONLY",
    account_ids: null,
    alert_scope: "AGGREGATE",
    sort_order: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeAccount(overrides: Partial<AssetAccount> = {}): AssetAccount {
  return {
    id: "a1",
    name: "키움 증권",
    asset_type: "STOCK_KIWOOM",
    data_source: "KIWOOM_API",
    institution: null,
    kis_account_no: null,
    kiwoom_account_no: "1234",
    is_mock_mode: false,
    manual_amount: null,
    manual_currency: "KRW",
    manual_updated_at: null,
    deposit_krw: 0,
    deposit_usd: null,
    real_estate_details: null,
    include_in_total: true,
    is_active: true,
    sort_order: 0,
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    has_own_kis_credentials: false,
    has_own_kiwoom_credentials: false,
    target_portfolio_id: null,
    tax_type: "GENERAL",
    ...overrides,
  };
}

function makeSettingsData(overrides: Partial<SettingsData> = {}): SettingsData {
  return {
    has_kis: false,
    has_dart: false,
    goal_amount: 100_000_000,
    goal_annual_return_pct: null,
    annual_deposit_goal: null,
    monthly_deposit_amount: null,
    retirement_target_year: 2040,
    user_email: "test@example.com",
    notification_email: null,
    annual_dividend_goal: null,
    fcm_token_stored: false,
    composite_signal_alerts_enabled: true,
    market_signal_daily_digest_enabled: false,
    year_end_tax_reminder_enabled: false,
    goal_achievement_alerts_enabled: true,
    monthly_report_enabled: true,
    goal_candidate_tickers: [],
    goal_risk_tolerance: "CONSERVATIVE",
    goal_max_weight_pct: 40.0,
    goal_cagr_lookback_years: 10,
    goal_short_term_equity_floor_pct: 80.0,
    auto_rebalancing_max_order_value_krw: 50_000_000.0,
    ...overrides,
  };
}

function makeOverallRecommendation(
  overrides: Partial<GoalRecommendation> = {},
): GoalRecommendation {
  return {
    generated_at: "2026-07-06T00:00:00Z",
    is_configured: true,
    required_return_pct: 8.5,
    required_dividend_yield_pct: null,
    recommended_items: [
      { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", weight: 60 },
      { ticker: "SCHD", name: "Schwab US Dividend Equity ETF", market: "NYSE", weight: 40 },
    ],
    expected_return_pct: 9.1,
    expected_dividend_yield_pct: 2.1,
    note: null,
    cagr_lookback_years: 10,
    risk_tolerance: "CONSERVATIVE",
    max_weight_pct: 40.0,
    market_signal_level: null,
    ...overrides,
  };
}

function makeHorizonRec(
  overrides: Partial<HorizonGoalRecommendation> = {},
): HorizonGoalRecommendation {
  return {
    investment_horizon: "SHORT_TERM",
    tax_type: "GENERAL",
    base_krw: 5_000_000,
    account_count: 1,
    recommended_items: [
      { ticker: "153130", name: "KODEX 단기채권", market: "KOSPI", weight: 60 },
      { ticker: "114260", name: "KODEX 국고채3년", market: "KOSPI", weight: 40 },
    ],
    expected_return_pct: 2.5,
    risk_tolerance: "CONSERVATIVE",
    max_weight_pct: 40,
    includes_cash_equivalent: false,
    market_signal_level: null,
    note: null,
    ...overrides,
  };
}

function makeHorizonResponse(
  recommendations: HorizonGoalRecommendation[],
): HorizonRecommendationResponse {
  return { generated_at: "2026-07-13T00:00:00Z", recommendations };
}

describe("RecommendationCard", () => {
  beforeEach(() => {
    fetchOverallGoalRecommendation.mockReset();
    fetchHorizonGoalRecommendations.mockReset();
    fetchHorizonGoalRecommendations.mockResolvedValue(makeHorizonResponse([]));
    fetchSettings.mockReset();
    fetchSettings.mockResolvedValue(makeSettingsData());
    updateGoalCandidateTickers.mockReset();
    updateGoalCandidateTickers.mockResolvedValue({ detail: "저장되었습니다" });
    updateGoalRecommendationOptions.mockReset();
    updateGoalRecommendationOptions.mockResolvedValue({ detail: "저장되었습니다" });
    fetchPortfolios.mockReset();
    fetchPortfolios.mockResolvedValue([]);
    fetchAccounts.mockReset();
    fetchAccounts.mockResolvedValue([]);
    updatePortfolio.mockReset();
    toastMock.mockReset();
    useStockSearchMock.mockReset();
    useStockSearchMock.mockReturnValue({
      suggestions: [],
      isSearching: false,
      search: vi.fn(),
      clearSuggestions: vi.fn(),
    });
  });

  describe("전체 탭 (목표 역산)", () => {
    it("shows the not-configured guidance instead of hiding the card", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(
        makeOverallRecommendation({ is_configured: false, recommended_items: [] }),
      );
      renderWithProviders(<RecommendationCard />);

      expect(await screen.findByText("추천 비중")).toBeDefined();
      expect(screen.getByText("전체")).toBeDefined();
      expect(
        await screen.findByText("목표금액·목표연도를 설정하면 추천을 받을 수 있습니다"),
      ).toBeDefined();
      expect(screen.queryByText(/에 적용/)).toBeNull();
    });

    it("shows the note and a candidate-manager entry point when there are no recommended items", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(
        makeOverallRecommendation({ recommended_items: [], note: "이미 목표 금액을 달성했습니다" }),
      );
      renderWithProviders(<RecommendationCard />);

      expect(await screen.findByText("이미 목표 금액을 달성했습니다")).toBeDefined();
      expect(screen.getByText(/후보 ETF 관리/)).toBeDefined();
      expect(screen.queryByText(/에 적용/)).toBeNull();
    });

    it("renders recommended items and required/expected return", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      renderWithProviders(<RecommendationCard />);

      expect(await screen.findByText(/SPY/)).toBeDefined();
      expect(screen.getByText("60.0%")).toBeDefined();
      expect(screen.getByText("40.0%")).toBeDefined();
      expect(screen.getByText(/최근 10년 CAGR 기준/)).toBeDefined();
    });

    it("shows a hint instead of an apply control when no portfolio is set as a goal target", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchPortfolios.mockResolvedValue([makePortfolio()]);
      fetchAccounts.mockResolvedValue([makeAccount({ target_portfolio_id: null })]);
      renderWithProviders(<RecommendationCard />);

      expect(
        await screen.findByText(
          "포트폴리오 탭에서 기준 포트폴리오를 지정하면 추천 비중을 바로 적용할 수 있어요.",
        ),
      ).toBeDefined();
      expect(screen.queryByText(/에 적용/)).toBeNull();
    });

    it("offers a create-new-portfolio button that reports normalized weights even without a target portfolio", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(
        makeOverallRecommendation({
          recommended_items: [
            { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", weight: 33.33 },
            {
              ticker: "SCHD",
              name: "Schwab US Dividend Equity ETF",
              market: "NYSE",
              weight: 66.67,
            },
          ],
        }),
      );
      const onCreatePortfolio = vi.fn();
      renderWithProviders(<RecommendationCard onCreatePortfolio={onCreatePortfolio} />);

      fireEvent.click(await screen.findByText("이 비중으로 새 포트폴리오 만들기"));

      expect(onCreatePortfolio).toHaveBeenCalledWith(
        [
          { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", weight: 33.3 },
          {
            ticker: "SCHD",
            name: "Schwab US Dividend Equity ETF",
            market: "NYSE",
            weight: 66.7,
          },
        ],
        "추천 포트폴리오",
      );
    });

    it("applies normalized recommended weights to the single target portfolio and reports success", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(
        makeOverallRecommendation({
          recommended_items: [
            { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", weight: 33.33 },
            {
              ticker: "SCHD",
              name: "Schwab US Dividend Equity ETF",
              market: "NYSE",
              weight: 33.33,
            },
            {
              ticker: "TLT",
              name: "iShares 20+ Year Treasury Bond ETF",
              market: "NYSE",
              weight: 33.33,
            },
          ],
        }),
      );
      const portfolio = makePortfolio({ id: "target-1", name: "은퇴 포트폴리오" });
      fetchPortfolios.mockResolvedValue([portfolio]);
      fetchAccounts.mockResolvedValue([makeAccount({ target_portfolio_id: "target-1" })]);
      updatePortfolio.mockResolvedValue({ ...portfolio, items: [] });
      const onApplied = vi.fn();

      renderWithProviders(<RecommendationCard onApplied={onApplied} />);

      fireEvent.click(await screen.findByText("은퇴 포트폴리오에 적용"));
      fireEvent.click(await screen.findByText("적용"));

      await waitFor(() => expect(updatePortfolio).toHaveBeenCalled());
      expect(updatePortfolio).toHaveBeenCalledWith("target-1", {
        items: [
          { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", weight: 33.3 },
          { ticker: "SCHD", name: "Schwab US Dividend Equity ETF", market: "NYSE", weight: 33.3 },
          {
            ticker: "TLT",
            name: "iShares 20+ Year Treasury Bond ETF",
            market: "NYSE",
            weight: 33.4,
          },
        ],
      });
      await waitFor(() => expect(onApplied).toHaveBeenCalledWith("target-1"));
    });

    it("requires selecting a target portfolio when multiple portfolios are goal targets", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchPortfolios.mockResolvedValue([
        makePortfolio({ id: "target-1", name: "국내 포트폴리오" }),
        makePortfolio({ id: "target-2", name: "해외 포트폴리오" }),
      ]);
      fetchAccounts.mockResolvedValue([
        makeAccount({ id: "a1", target_portfolio_id: "target-1" }),
        makeAccount({ id: "a2", target_portfolio_id: "target-2" }),
      ]);
      updatePortfolio.mockResolvedValue({});
      const onApplied = vi.fn();

      renderWithProviders(<RecommendationCard onApplied={onApplied} />);

      const applyButton = await screen.findByText("기준 포트폴리오에 적용");
      expect(applyButton.closest("button")).toBeDisabled();

      fireEvent.change(screen.getByDisplayValue("포트폴리오 선택"), {
        target: { value: "target-2" },
      });
      expect(applyButton.closest("button")).not.toBeDisabled();

      fireEvent.click(applyButton);
      fireEvent.click(await screen.findByText("적용"));

      await waitFor(() =>
        expect(updatePortfolio).toHaveBeenCalledWith("target-2", expect.anything()),
      );
    });

    it("toasts an error and does not report success when saving the recommendation fails", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchPortfolios.mockResolvedValue([makePortfolio({ id: "target-1" })]);
      fetchAccounts.mockResolvedValue([makeAccount({ target_portfolio_id: "target-1" })]);
      updatePortfolio.mockRejectedValue(new Error("저장 실패"));
      const onApplied = vi.fn();

      renderWithProviders(<RecommendationCard onApplied={onApplied} />);

      fireEvent.click(await screen.findByText(/에 적용/));
      fireEvent.click(await screen.findByText("적용"));

      await waitFor(() => expect(toastMock).toHaveBeenCalled());
      expect(onApplied).not.toHaveBeenCalled();
    });

    it("renders a clamp note alongside a successful recommendation", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(
        makeOverallRecommendation({
          note: "선택한 리스크 성향의 여유 수익률 목표는 종목당 최대 비중 제약 하에서 달성 가능한 최대 기대수익률까지만 반영되었습니다",
        }),
      );
      renderWithProviders(<RecommendationCard />);

      expect(
        await screen.findByText(
          "선택한 리스크 성향의 여유 수익률 목표는 종목당 최대 비중 제약 하에서 달성 가능한 최대 기대수익률까지만 반영되었습니다",
        ),
      ).toBeDefined();
    });
  });

  describe("추천 비중 변화 배지 (계획 3)", () => {
    it("shows a drift badge when the applied portfolio has different tickers than the recommendation", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      const portfolio = makePortfolio({
        id: "target-1",
        items: [{ ticker: "AAPL", name: "Apple", market: "NASDAQ", weight: 100 }],
      });
      fetchPortfolios.mockResolvedValue([portfolio]);
      fetchAccounts.mockResolvedValue([makeAccount({ target_portfolio_id: "target-1" })]);
      renderWithProviders(<RecommendationCard />);

      expect(await screen.findByText(/추천 비중이 달라졌어요/)).toBeDefined();
      expect(screen.getByText(/신규 후보 2개/)).toBeDefined();
    });

    it("does not show a drift badge when the applied portfolio already matches the recommendation", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      const portfolio = makePortfolio({
        id: "target-1",
        items: [
          { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", weight: 60 },
          { ticker: "SCHD", name: "Schwab US Dividend Equity ETF", market: "NYSE", weight: 40 },
        ],
      });
      fetchPortfolios.mockResolvedValue([portfolio]);
      fetchAccounts.mockResolvedValue([makeAccount({ target_portfolio_id: "target-1" })]);
      renderWithProviders(<RecommendationCard />);

      await screen.findByText(/SPY/);
      expect(screen.queryByText(/추천 비중이 달라졌어요/)).toBeNull();
    });

    it("shows a drift badge with the max delta for the active horizon recommendation", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(makeHorizonResponse([makeHorizonRec()]));
      const portfolio = makePortfolio({
        id: "target-1",
        name: "단기 포트폴리오",
        items: [
          { ticker: "153130", name: "KODEX 단기채권", market: "KOSPI", weight: 50 },
          { ticker: "114260", name: "KODEX 국고채3년", market: "KOSPI", weight: 50 },
        ],
      });
      fetchPortfolios.mockResolvedValue([portfolio]);
      fetchAccounts.mockResolvedValue([
        makeAccount({ target_portfolio_id: "target-1", investment_horizon: "SHORT_TERM" }),
      ]);
      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText("단기"));

      expect(await screen.findByText(/최대 10%p 차이/)).toBeDefined();
    });

    it("does not show a drift badge for the horizon tab when weights already match", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(makeHorizonResponse([makeHorizonRec()]));
      const portfolio = makePortfolio({
        id: "target-1",
        name: "단기 포트폴리오",
        items: [
          { ticker: "153130", name: "KODEX 단기채권", market: "KOSPI", weight: 60 },
          { ticker: "114260", name: "KODEX 국고채3년", market: "KOSPI", weight: 40 },
        ],
      });
      fetchPortfolios.mockResolvedValue([portfolio]);
      fetchAccounts.mockResolvedValue([
        makeAccount({ target_portfolio_id: "target-1", investment_horizon: "SHORT_TERM" }),
      ]);
      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText("단기"));
      await screen.findByText(/KODEX 단기채권/);

      expect(screen.queryByText(/추천 비중이 달라졌어요/)).toBeNull();
    });
  });

  describe("후보 ETF 관리 / 추천 설정 (공용 영역)", () => {
    it("shows previously saved candidate ETFs when the manager panel is expanded", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchSettings.mockResolvedValue(
        makeSettingsData({
          goal_candidate_tickers: [
            { ticker: "TLT", name: "iShares 20+ Year Treasury Bond ETF", market: "NYSE" },
          ],
        }),
      );
      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText(/후보 ETF 관리/));

      expect(await screen.findByText(/TLT/)).toBeDefined();
    });

    it("adds a searched candidate and saves the merged list", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      useStockSearchMock.mockReturnValue({
        suggestions: [
          {
            ticker: "TLT",
            name: "iShares 20+ Year Treasury Bond ETF",
            market: "NYSE",
            exchange: "NASDAQ",
          },
        ],
        isSearching: false,
        search: vi.fn(),
        clearSuggestions: vi.fn(),
      });
      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText(/후보 ETF 관리/));
      fireEvent.change(screen.getByPlaceholderText("추가할 ETF 종목명 또는 코드 검색"), {
        target: { value: "TLT" },
      });
      fireEvent.mouseDown(await screen.findByText("iShares 20+ Year Treasury Bond ETF"));

      fireEvent.click(await screen.findByText("저장"));

      await waitFor(() => expect(updateGoalCandidateTickers).toHaveBeenCalled());
      expect(updateGoalCandidateTickers.mock.calls[0][0]).toEqual([
        {
          ticker: "TLT",
          name: "iShares 20+ Year Treasury Bond ETF",
          market: "NYSE",
          asset_class: "EQUITY",
        },
      ]);
    });

    it("opens the recommendation-options modal and saves risk tolerance changes", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText("추천 설정"));
      expect(await screen.findByText("리스크 성향")).toBeDefined();

      fireEvent.change(screen.getByDisplayValue("보수적 (목표치 그대로)"), {
        target: { value: "AGGRESSIVE" },
      });
      fireEvent.click(await screen.findByText("저장"));

      await waitFor(() => expect(updateGoalRecommendationOptions).toHaveBeenCalled());
      expect(updateGoalRecommendationOptions.mock.calls[0][0]).toEqual({
        risk_tolerance: "AGGRESSIVE",
        max_weight_pct: 40,
        cagr_lookback_years: 10,
        short_term_equity_floor_pct: 80,
      });
    });

    it("stays visible after switching to a horizon tab", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(
        makeHorizonResponse([makeHorizonRec({ investment_horizon: "SHORT_TERM" })]),
      );
      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText("단기"));

      expect(await screen.findByText(/후보 ETF 관리/)).toBeDefined();
      expect(screen.getByText("추천 설정")).toBeDefined();
    });
  });

  describe("기간별 탭 (단기/중기/장기)", () => {
    it("shows only the 전체 tab when no horizon has tagged accounts", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(makeHorizonResponse([]));
      renderWithProviders(<RecommendationCard />);

      await screen.findByText("전체");
      expect(screen.queryByText("단기")).toBeNull();
      expect(screen.queryByText("중기")).toBeNull();
      expect(screen.queryByText("장기")).toBeNull();
    });

    it("shows only the pills for horizons present in the response", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(
        makeHorizonResponse([makeHorizonRec({ investment_horizon: "SHORT_TERM" })]),
      );
      renderWithProviders(<RecommendationCard />);

      expect(await screen.findByText("단기")).toBeDefined();
      expect(screen.queryByText("중기")).toBeNull();
      expect(screen.queryByText("장기")).toBeNull();
    });

    it("renders recommended items for the selected horizon after switching tabs", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(makeHorizonResponse([makeHorizonRec()]));
      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText("단기"));

      expect(await screen.findByText(/KODEX 단기채권/)).toBeDefined();
      expect(screen.getByText("60.0%")).toBeDefined();
      expect(screen.getByText("40.0%")).toBeDefined();
    });

    it("switches displayed recommendation when another horizon pill is clicked", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(
        makeHorizonResponse([
          makeHorizonRec({ investment_horizon: "SHORT_TERM" }),
          makeHorizonRec({
            investment_horizon: "LONG_TERM",
            risk_tolerance: "AGGRESSIVE",
            recommended_items: [
              { ticker: "QQQ", name: "Invesco QQQ Trust", market: "NASDAQ", weight: 100 },
            ],
          }),
        ]),
      );
      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText("단기"));
      await screen.findByText(/KODEX 단기채권/);
      fireEvent.click(screen.getByText("장기"));

      expect(await screen.findByText(/Invesco QQQ Trust/)).toBeDefined();
      expect(screen.queryByText(/KODEX 단기채권/)).toBeNull();
    });

    it("shows a note instead of items when the recommendation is insufficient", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(
        makeHorizonResponse([
          makeHorizonRec({
            investment_horizon: "MID_TERM",
            recommended_items: [],
            note: "이 기간에 적합한 후보가 부족합니다 — 후보 ETF 관리에서 채권/현금성 ETF를 추가해주세요",
          }),
        ]),
      );
      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText("중기"));

      expect(
        await screen.findByText(
          "이 기간에 적합한 후보가 부족합니다 — 후보 ETF 관리에서 채권/현금성 ETF를 추가해주세요",
        ),
      ).toBeDefined();
    });

    it("falls back to a 100% cash-equivalent recommendation when no bond/cash ETF is registered", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(
        makeHorizonResponse([
          makeHorizonRec({
            recommended_items: [
              {
                ticker: "CASH_EQUIVALENT",
                name: "현금성 자산 (CMA·파킹통장 등)",
                market: "CASH",
                weight: 100,
              },
            ],
            includes_cash_equivalent: true,
            note: "채권/현금성 ETF 후보가 등록되어 있지 않아 현금성 자산(CMA·파킹통장 등)으로 전액 배분을 권장합니다.",
          }),
        ]),
      );
      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText("단기"));

      expect(await screen.findByText(/현금성 자산 \(CMA·파킹통장 등\)/)).toBeDefined();
      expect(screen.getByText("100.0%")).toBeDefined();
      expect(screen.queryByText(/CASH_EQUIVALENT/)).toBeNull();
      expect(await screen.findByText(/채권\/현금성 ETF 후보가 등록되어 있지 않아/)).toBeDefined();
      expect(screen.queryByText(/에 적용/)).toBeNull();
    });

    it("shows a hint instead of an apply button when no portfolio matches the horizon tag", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(makeHorizonResponse([makeHorizonRec()]));
      fetchPortfolios.mockResolvedValue([makePortfolio()]);
      fetchAccounts.mockResolvedValue([makeAccount({ target_portfolio_id: null })]);
      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText("단기"));
      await screen.findByText(/KODEX 단기채권/);

      expect(
        await screen.findByText(/포트폴리오 탭에서 이 기간·계좌유형에 해당하는 계좌를 태그하고/),
      ).toBeDefined();
      expect(screen.queryByText(/에 적용/)).toBeNull();
    });

    it("offers a create-new-portfolio button for the active horizon even without a matching portfolio", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(makeHorizonResponse([makeHorizonRec()]));
      const onCreatePortfolio = vi.fn();
      renderWithProviders(<RecommendationCard onCreatePortfolio={onCreatePortfolio} />);

      fireEvent.click(await screen.findByText("단기"));
      fireEvent.click(await screen.findByText("이 비중으로 새 포트폴리오 만들기"));

      expect(onCreatePortfolio).toHaveBeenCalledWith(
        [
          { ticker: "153130", name: "KODEX 단기채권", market: "KOSPI", weight: 60 },
          { ticker: "114260", name: "KODEX 국고채3년", market: "KOSPI", weight: 40 },
        ],
        "단기 추천 포트폴리오",
        [],
      );
    });

    it("passes only the accounts tagged with the active horizon/tax type when creating a new portfolio", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(makeHorizonResponse([makeHorizonRec()]));
      fetchAccounts.mockResolvedValue([
        makeAccount({ id: "a-match", investment_horizon: "SHORT_TERM", tax_type: "GENERAL" }),
        makeAccount({
          id: "a-other-horizon",
          investment_horizon: "LONG_TERM",
          tax_type: "GENERAL",
        }),
        makeAccount({ id: "a-other-tax", investment_horizon: "SHORT_TERM", tax_type: "ISA" }),
        makeAccount({ id: "a-untagged" }),
      ]);
      const onCreatePortfolio = vi.fn();
      renderWithProviders(<RecommendationCard onCreatePortfolio={onCreatePortfolio} />);

      fireEvent.click(await screen.findByText("단기"));
      fireEvent.click(await screen.findByText("이 비중으로 새 포트폴리오 만들기"));

      expect(onCreatePortfolio).toHaveBeenCalledWith(expect.anything(), expect.anything(), [
        "a-match",
      ]);
    });

    it("does not offer a create-new-portfolio button for cash-equivalent recommendations with no matching CMA account", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(
        makeHorizonResponse([
          makeHorizonRec({
            recommended_items: [
              {
                ticker: "CASH_EQUIVALENT",
                name: "현금성 자산 (CMA·파킹통장 등)",
                market: "CASH",
                weight: 100,
              },
            ],
            includes_cash_equivalent: true,
          }),
        ]),
      );
      const onCreatePortfolio = vi.fn();
      renderWithProviders(<RecommendationCard onCreatePortfolio={onCreatePortfolio} />);

      fireEvent.click(await screen.findByText("단기"));
      await screen.findByText(/현금성 자산 \(CMA·파킹통장 등\)/);

      expect(screen.queryByText("이 비중으로 새 포트폴리오 만들기")).toBeNull();
      expect(
        await screen.findByText(/CMA\/파킹통장 계좌에.*기간 태그를 지정하면 자동 적용할 수 있어요/),
      ).toBeDefined();
    });

    it("offers apply/create controls and links the matching CMA account when one is tagged for the horizon", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(
        makeHorizonResponse([
          makeHorizonRec({
            recommended_items: [
              {
                ticker: "CASH_EQUIVALENT",
                name: "현금성 자산 (CMA·파킹통장 등)",
                market: "CASH",
                weight: 100,
              },
            ],
            includes_cash_equivalent: true,
          }),
        ]),
      );
      fetchAccounts.mockResolvedValue([
        makeAccount({
          id: "bank-1",
          name: "토스뱅크 파킹통장",
          asset_type: "BANK_ACCOUNT",
          investment_horizon: "SHORT_TERM",
          tax_type: "GENERAL",
        }),
      ]);
      const onCreatePortfolio = vi.fn();
      renderWithProviders(<RecommendationCard onCreatePortfolio={onCreatePortfolio} />);

      fireEvent.click(await screen.findByText("단기"));
      await screen.findByText(/현금성 자산 \(CMA·파킹통장 등\)/);

      expect(
        await screen.findByText(/현금성 자산 반영을 위해.*토스뱅크 파킹통장.*계좌가 포트폴리오에/),
      ).toBeDefined();

      fireEvent.click(await screen.findByText("이 비중으로 새 포트폴리오 만들기"));

      expect(onCreatePortfolio).toHaveBeenCalledWith(
        [
          {
            ticker: "CASH_EQUIVALENT",
            name: "현금성 자산 (CMA·파킹통장 등)",
            market: "CASH",
            weight: 100,
          },
        ],
        "단기 추천 포트폴리오",
        ["bank-1"],
      );
    });

    it("merges the matching CMA account into account_ids when applying a cash-equivalent recommendation to an account-scoped portfolio", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(
        makeHorizonResponse([
          makeHorizonRec({
            recommended_items: [
              {
                ticker: "CASH_EQUIVALENT",
                name: "현금성 자산 (CMA·파킹통장 등)",
                market: "CASH",
                weight: 100,
              },
            ],
            includes_cash_equivalent: true,
          }),
        ]),
      );
      const portfolio = makePortfolio({
        id: "target-1",
        name: "단기 포트폴리오",
        account_ids: ["stock-1"],
      });
      fetchPortfolios.mockResolvedValue([portfolio]);
      fetchAccounts.mockResolvedValue([
        makeAccount({
          id: "stock-1",
          target_portfolio_id: "target-1",
          investment_horizon: "SHORT_TERM",
        }),
        makeAccount({
          id: "bank-1",
          asset_type: "BANK_ACCOUNT",
          investment_horizon: "SHORT_TERM",
          tax_type: "GENERAL",
        }),
      ]);
      updatePortfolio.mockResolvedValue({ ...portfolio, items: [] });
      const onApplied = vi.fn();

      renderWithProviders(<RecommendationCard onApplied={onApplied} />);

      fireEvent.click(await screen.findByText("단기"));
      fireEvent.click(await screen.findByText("단기 포트폴리오에 적용"));
      fireEvent.click(await screen.findByText("적용"));

      await waitFor(() => expect(updatePortfolio).toHaveBeenCalled());
      expect(updatePortfolio).toHaveBeenCalledWith("target-1", {
        items: [
          {
            ticker: "CASH_EQUIVALENT",
            name: "현금성 자산 (CMA·파킹통장 등)",
            market: "CASH",
            weight: 100,
          },
        ],
        account_ids: ["stock-1", "bank-1"],
      });
      await waitFor(() => expect(onApplied).toHaveBeenCalledWith("target-1"));
    });

    it("does not send account_ids when applying a cash-equivalent recommendation to an all-accounts portfolio", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(
        makeHorizonResponse([
          makeHorizonRec({
            recommended_items: [
              {
                ticker: "CASH_EQUIVALENT",
                name: "현금성 자산 (CMA·파킹통장 등)",
                market: "CASH",
                weight: 100,
              },
            ],
            includes_cash_equivalent: true,
          }),
        ]),
      );
      const portfolio = makePortfolio({
        id: "target-1",
        name: "단기 포트폴리오",
        account_ids: null,
      });
      fetchPortfolios.mockResolvedValue([portfolio]);
      fetchAccounts.mockResolvedValue([
        makeAccount({
          id: "stock-1",
          target_portfolio_id: "target-1",
          investment_horizon: "SHORT_TERM",
        }),
        makeAccount({
          id: "bank-1",
          asset_type: "BANK_ACCOUNT",
          investment_horizon: "SHORT_TERM",
          tax_type: "GENERAL",
        }),
      ]);
      updatePortfolio.mockResolvedValue({ ...portfolio, items: [] });

      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText("단기"));
      fireEvent.click(await screen.findByText("단기 포트폴리오에 적용"));
      fireEvent.click(await screen.findByText("적용"));

      await waitFor(() => expect(updatePortfolio).toHaveBeenCalled());
      expect(updatePortfolio).toHaveBeenCalledWith("target-1", {
        items: [
          {
            ticker: "CASH_EQUIVALENT",
            name: "현금성 자산 (CMA·파킹통장 등)",
            market: "CASH",
            weight: 100,
          },
        ],
      });
    });

    it("applies the recommendation to the portfolio inferred from matching account horizon tags", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(makeHorizonResponse([makeHorizonRec()]));
      const portfolio = makePortfolio({ id: "target-1", name: "단기 포트폴리오" });
      fetchPortfolios.mockResolvedValue([portfolio]);
      fetchAccounts.mockResolvedValue([
        makeAccount({ target_portfolio_id: "target-1", investment_horizon: "SHORT_TERM" }),
      ]);
      updatePortfolio.mockResolvedValue({ ...portfolio, items: [] });
      const onApplied = vi.fn();

      renderWithProviders(<RecommendationCard onApplied={onApplied} />);

      fireEvent.click(await screen.findByText("단기"));
      fireEvent.click(await screen.findByText("단기 포트폴리오에 적용"));
      fireEvent.click(await screen.findByText("적용"));

      await waitFor(() => expect(updatePortfolio).toHaveBeenCalled());
      expect(updatePortfolio).toHaveBeenCalledWith("target-1", {
        items: [
          { ticker: "153130", name: "KODEX 단기채권", market: "KOSPI", weight: 60 },
          { ticker: "114260", name: "KODEX 국고채3년", market: "KOSPI", weight: 40 },
        ],
      });
      await waitFor(() => expect(onApplied).toHaveBeenCalledWith("target-1"));
    });

    it("does not offer an apply button when a matching portfolio's account horizons are mixed", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(makeHorizonResponse([makeHorizonRec()]));
      fetchPortfolios.mockResolvedValue([makePortfolio({ id: "target-1" })]);
      fetchAccounts.mockResolvedValue([
        makeAccount({
          id: "a1",
          target_portfolio_id: "target-1",
          investment_horizon: "SHORT_TERM",
        }),
        makeAccount({ id: "a2", target_portfolio_id: "target-1", investment_horizon: "LONG_TERM" }),
      ]);
      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText("단기"));
      await screen.findByText(/KODEX 단기채권/);
      expect(screen.queryByText(/에 적용/)).toBeNull();
    });

    it("toasts an error and does not report success when saving a horizon recommendation fails", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(makeHorizonResponse([makeHorizonRec()]));
      fetchPortfolios.mockResolvedValue([makePortfolio({ id: "target-1" })]);
      fetchAccounts.mockResolvedValue([
        makeAccount({ target_portfolio_id: "target-1", investment_horizon: "SHORT_TERM" }),
      ]);
      updatePortfolio.mockRejectedValue(new Error("저장 실패"));
      const onApplied = vi.fn();

      renderWithProviders(<RecommendationCard onApplied={onApplied} />);

      fireEvent.click(await screen.findByText("단기"));
      fireEvent.click(await screen.findByText(/에 적용/));
      fireEvent.click(await screen.findByText("적용"));

      await waitFor(() => expect(toastMock).toHaveBeenCalled());
      expect(onApplied).not.toHaveBeenCalled();
    });

    it("splits recommendations by tax type within the same horizon and switches on chip click", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(
        makeHorizonResponse([
          makeHorizonRec({
            investment_horizon: "LONG_TERM",
            tax_type: "ISA",
            recommended_items: [
              { ticker: "069500", name: "KODEX 200", market: "KOSPI", weight: 100 },
            ],
          }),
          makeHorizonRec({
            investment_horizon: "LONG_TERM",
            tax_type: "OVERSEAS_DEDICATED",
            recommended_items: [
              { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", weight: 100 },
            ],
          }),
        ]),
      );
      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText("장기"));

      expect(await screen.findByText(/KODEX 200/)).toBeDefined();
      expect(screen.getByText("ISA")).toBeDefined();
      expect(screen.getByText("해외전용")).toBeDefined();

      fireEvent.click(screen.getByText("해외전용"));

      expect(await screen.findByText(/SPDR S&P 500 ETF/)).toBeDefined();
      expect(screen.queryByText(/KODEX 200/)).toBeNull();
    });

    it("applies to the portfolio matching both the active horizon and tax type", async () => {
      fetchOverallGoalRecommendation.mockResolvedValue(makeOverallRecommendation());
      fetchHorizonGoalRecommendations.mockResolvedValue(
        makeHorizonResponse([
          makeHorizonRec({
            investment_horizon: "LONG_TERM",
            tax_type: "ISA",
            recommended_items: [
              { ticker: "069500", name: "KODEX 200", market: "KOSPI", weight: 100 },
            ],
          }),
          makeHorizonRec({
            investment_horizon: "LONG_TERM",
            tax_type: "GENERAL",
            recommended_items: [
              { ticker: "005930", name: "삼성전자", market: "KOSPI", weight: 100 },
            ],
          }),
        ]),
      );
      fetchPortfolios.mockResolvedValue([
        makePortfolio({ id: "isa-portfolio", name: "ISA 포트폴리오" }),
        makePortfolio({ id: "general-portfolio", name: "일반 포트폴리오" }),
      ]);
      fetchAccounts.mockResolvedValue([
        makeAccount({
          id: "isa-acc",
          target_portfolio_id: "isa-portfolio",
          investment_horizon: "LONG_TERM",
          tax_type: "ISA",
        }),
        makeAccount({
          id: "general-acc",
          target_portfolio_id: "general-portfolio",
          investment_horizon: "LONG_TERM",
          tax_type: "GENERAL",
        }),
      ]);
      updatePortfolio.mockResolvedValue({});

      renderWithProviders(<RecommendationCard />);

      fireEvent.click(await screen.findByText("장기"));

      expect(await screen.findByText("일반 포트폴리오에 적용")).toBeDefined();

      fireEvent.click(screen.getByText("ISA"));

      expect(await screen.findByText("ISA 포트폴리오에 적용")).toBeDefined();
      expect(screen.queryByText("일반 포트폴리오에 적용")).toBeNull();
    });
  });
});
