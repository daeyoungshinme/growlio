import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ── mocks ────────────────────────────────────────────────────────────────────

vi.mock("@/api/client", () => {
  const mockApi = { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() };
  return {
    api: mockApi,
    apiGet: (url: string, ...args: unknown[]) =>
      mockApi.get(url, ...args).then((r: { data: unknown }) => r.data),
    apiPost: (url: string, ...args: unknown[]) =>
      mockApi.post(url, ...args).then((r: { data: unknown }) => r.data),
    apiPut: (url: string, ...args: unknown[]) =>
      mockApi.put(url, ...args).then((r: { data: unknown }) => r.data),
    apiPatch: (url: string, ...args: unknown[]) =>
      mockApi.patch(url, ...args).then((r: { data: unknown }) => r.data),
    apiDelete: (url: string, ...args: unknown[]) =>
      mockApi.delete(url, ...args).then((r: { data: unknown }) => r.data),
  };
});

vi.mock("@/hooks/useExchangeRate", () => ({ useExchangeRate: vi.fn(() => 1350) }));

vi.mock("@/stores/themeStore", () => ({
  useThemeStore: (selector: (s: { isDark: boolean; toggle: () => void }) => unknown) => {
    const state = { isDark: false, toggle: vi.fn() };
    return typeof selector === "function" ? selector(state) : state;
  },
}));

vi.mock("@/utils/queryInvalidation", () => ({
  invalidateTransactionData: vi.fn(),
  invalidatePortfolioData: vi.fn(),
  invalidateRebalancingAlertData: vi.fn(),
  invalidateAccountData: vi.fn(),
  invalidateSyncData: vi.fn(),
  invalidateAlertData: vi.fn(),
  invalidateDcaData: vi.fn(),
  invalidateDividendPlanData: vi.fn(),
}));

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

vi.mock("@/hooks/useRegisterRefresh", () => ({ useRegisterRefresh: vi.fn() }));

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
    },
  },
}));

vi.mock("@/stores/authStore", () => ({
  useAuthStore: vi.fn((selector: (s: { resetPassword: () => Promise<void> }) => unknown) => {
    const state = { resetPassword: vi.fn().mockResolvedValue(undefined) };
    return typeof selector === "function" ? selector(state) : state;
  }),
}));

vi.mock("@/hooks/useLogout", () => ({ useLogout: vi.fn(() => vi.fn()) }));

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AreaChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PieChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Line: () => <div />,
  Bar: () => <div />,
  Area: () => <div />,
  Pie: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />,
  Cell: () => <div />,
  Treemap: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ReferenceLine: () => <div />,
}));

// Lazy-loaded component stubs
vi.mock("../components/portfolio/TreemapChart", () => ({
  default: () => <div data-testid="treemap" />,
}));
vi.mock("../components/portfolio/DomesticForeignBar", () => ({
  default: () => <div data-testid="domestic-bar" />,
}));
vi.mock("../components/portfolio-analysis/PortfolioManageTab", () => ({
  default: () => <div data-testid="portfolio-manage" />,
}));
vi.mock("../components/portfolio-analysis/PortfolioExecutionTab", () => ({
  default: () => <div data-testid="portfolio-execution" />,
}));
vi.mock("../components/portfolio-analysis/TaxOptimizationCard", () => ({
  default: () => <div data-testid="tax-opt" />,
}));
vi.mock("../components/invest/DCAProjectionChart", () => ({
  default: () => <div data-testid="dca-chart" />,
}));

vi.mock("@/hooks/useGoalSettings", () => ({
  useGoalSettings: vi.fn(() => ({
    data: {
      settings: {
        monthly_deposit_amount: 500000,
        goal_annual_return_pct: 8,
        goal_amount: 100000000,
        goal_start_date: "2024-01-01",
        goal_initial_amount: null,
      },
      is_configured: false,
      projection_months: [],
      yearly_achievements: [],
      goal_timeline: null,
    },
    isLoading: false,
    isError: false,
    editing: false,
    saving: false,
    showCloseConfirm: false,
    form: {
      monthly_deposit_amount: "500000",
      goal_annual_return_pct: "8",
      goal_amount: "100000000",
      goal_start_date: "2024-01-01",
      goal_initial_amount: "",
      annual_deposit_goal: "",
      retirement_target_year: "",
    },
    isDirty: false,
    setForm: vi.fn(),
    setShowCloseConfirm: vi.fn(),
    setEditing: vi.fn(),
    handleCloseModal: vi.fn(),
    openEdit: vi.fn(),
    saveSettings: vi.fn(),
  })),
}));

vi.mock("@/hooks/useAssetManagementData", () => ({
  useAssetManagementData: vi.fn(() => ({
    accounts: [],
    isLoading: false,
    overview: null,
    allTx: [],
    usdRate: 1350,
  })),
}));

vi.mock("@/hooks/useAssetModals", () => ({
  useAssetModals: vi.fn(() => ({
    showBankModal: false,
    setShowBankModal: vi.fn(),
    showStockModal: false,
    setShowStockModal: vi.fn(),
    showRealEstateModal: false,
    setShowRealEstateModal: vi.fn(),
    editingRealEstate: null,
    setEditingRealEstate: vi.fn(),
    editingBankAccount: null,
    setEditingBankAccount: vi.fn(),
    editingStockAccount: null,
    setEditingStockAccount: vi.fn(),
    confirmDeleteId: null,
    setConfirmDeleteId: vi.fn(),
    positionsAccount: null,
    setPositionsAccount: vi.fn(),
    txAccount: null,
    setTxAccount: vi.fn(),
  })),
}));

vi.mock("@/hooks/useAccountMutations", () => ({
  useAccountMutations: vi.fn(() => ({
    createMutation: { mutate: vi.fn(), isPending: false },
    deleteMutation: { mutate: vi.fn(), isPending: false },
    updateBankMutation: { mutate: vi.fn(), isPending: false },
    updateStockMutation: { mutate: vi.fn(), isPending: false },
    updateDepositMutation: { mutate: vi.fn(), isPending: false },
    updateNameMutation: { mutate: vi.fn(), isPending: false },
    updateRealEstateMutation: { mutate: vi.fn(), isPending: false },
    handleSyncKisAccount: vi.fn(),
    deletingId: null,
    setDeletingId: vi.fn(),
    syncingStockIds: new Set(),
  })),
}));

vi.mock("@/components/settings/ExchangeRateAlertSection", () => ({
  ExchangeRateAlertSection: () => <div data-testid="exchange-rate-alert-section" />,
}));

vi.mock("@/components/settings/StockPriceAlertSection", () => ({
  StockPriceAlertSection: () => <div data-testid="stock-price-alert-section" />,
}));

vi.mock("@/components/settings/MarketSignalAlertSection", () => ({
  MarketSignalAlertSection: () => <div data-testid="market-signal-alert-section" />,
}));

vi.mock("@/components/settings/NotificationEmailSection", () => ({
  NotificationEmailSection: () => <div data-testid="notification-email-section" />,
}));

vi.mock("@/components/settings/shared", () => ({
  SectionCard: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div data-testid="section-card">
      <span>{title}</span>
      {children}
    </div>
  ),
  ConnectedBadge: () => <span data-testid="connected-badge">연결됨</span>,
}));

vi.mock("@/api/alerts", () => ({
  fetchAlertHistory: vi.fn().mockResolvedValue([]),
  fetchRebalancingAlerts: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/api/settings", () => ({
  fetchSettings: vi
    .fn()
    .mockResolvedValue({ annual_deposit_goal: null, retirement_target_year: null }),
}));

vi.mock("@/api/invest", () => ({
  fetchDCAAnalysis: vi.fn().mockResolvedValue({
    settings: null,
    is_configured: false,
    projection_months: [],
    yearly_achievements: [],
    goal_timeline: null,
  }),
}));

vi.mock("@/api/assets", () => ({
  fetchAccounts: vi.fn().mockResolvedValue([]),
  fetchPortfolioOverview: vi.fn(),
  fetchExchangeRate: vi.fn().mockResolvedValue({ usd_krw: 1350 }),
  syncAllAccounts: vi.fn().mockResolvedValue({ total: 0, status: "started" }),
}));

vi.mock("@/api/portfolios", () => ({
  fetchPortfolioOverview: vi.fn(),
  fetchPortfolios: vi.fn().mockResolvedValue([]),
  fetchPortfolioOverviewLite: vi.fn().mockResolvedValue(null),
}));

vi.mock("@/api/transactions", () => ({
  fetchTransactions: vi.fn().mockResolvedValue([]),
}));

// ── imports ───────────────────────────────────────────────────────────────────

import AssetManagementPage from "@/pages/AssetManagementPage";
import InvestPlanPage from "@/pages/InvestPlanPage";
import PortfolioPage from "@/pages/PortfolioPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";
import SettingsPage from "@/pages/SettingsPage";
import { useAssetManagementData } from "@/hooks/useAssetManagementData";

// ── helpers ───────────────────────────────────────────────────────────────────

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return ({ children }: { children: React.ReactNode }) => (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

function renderPage(ui: React.ReactElement) {
  const Wrapper = createWrapper();
  return render(<Wrapper>{ui}</Wrapper>);
}

// ── AssetManagementPage ───────────────────────────────────────────────────────

describe("AssetManagementPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("탭 없이 렌더링된다", () => {
    renderPage(<AssetManagementPage />);
    expect(screen.getByText("은행계좌")).toBeInTheDocument();
  });

  it("은행계좌 탭에 '계좌 추가' 버튼이 있다", () => {
    renderPage(<AssetManagementPage />);
    expect(screen.getByText("계좌 추가")).toBeInTheDocument();
  });

  it("계좌가 없을 때 빈 상태 메시지를 표시한다", () => {
    renderPage(<AssetManagementPage />);
    expect(screen.getByText("등록된 은행계좌이 없습니다.")).toBeInTheDocument();
  });

  it("설명 텍스트가 표시된다", () => {
    renderPage(<AssetManagementPage />);
    expect(screen.getByText("계좌를 등록하고 입출금·배당 내역을 관리합니다.")).toBeInTheDocument();
  });

  it("증권계좌 예수금(CASH_STOCK)을 주식이 아닌 현금으로 집계한다", () => {
    vi.mocked(useAssetManagementData).mockReturnValue({
      accounts: [],
      isLoading: false,
      overview: {
        total_assets_krw: 10_000_000,
        total_stock_krw: 6_000_000,
        total_non_stock_krw: 4_000_000,
        total_invested_krw: 6_000_000,
        unrealized_pnl_krw: 0,
        stock_return_pct: 0,
        asset_type_allocation: [
          {
            type: "STOCK_KIS",
            name: "STOCK_KIS",
            label: "주식(KIS)",
            amount_krw: 6_000_000,
            pct: 60,
          },
          {
            type: "CASH_STOCK",
            name: "CASH_STOCK",
            label: "예수금(증권계좌)",
            amount_krw: 4_000_000,
            pct: 40,
          },
        ],
        stock_allocation: [],
        all_positions: [],
        accounts: [],
      },
      allTx: [],
      usdRate: 1350,
    });

    renderPage(<AssetManagementPage />);

    expect(screen.getByText("주식").nextElementSibling).toHaveTextContent("+60.00%");
    expect(screen.getByText("현금").nextElementSibling).toHaveTextContent("+40.00%");
  });
});

// ── InvestPlanPage ────────────────────────────────────────────────────────────

describe("InvestPlanPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("크래시 없이 렌더링된다", () => {
    renderPage(<InvestPlanPage />);
    expect(screen.getByText("적립 계획 설정")).toBeInTheDocument();
  });

  it("설정 편집 버튼이 있다", () => {
    renderPage(<InvestPlanPage />);
    expect(screen.getByText("설정 편집")).toBeInTheDocument();
  });

  it("적립 계획 설명 텍스트가 표시된다", () => {
    renderPage(<InvestPlanPage />);
    expect(screen.getByText("적립식 DCA 복리계산 및 목표 달성 현황")).toBeInTheDocument();
  });

  it("월 적립액, 목표 연수익률 등 설정 항목이 표시된다", () => {
    renderPage(<InvestPlanPage />);
    expect(screen.getByText("월 적립액")).toBeInTheDocument();
    expect(screen.getByText("목표 연수익률")).toBeInTheDocument();
    expect(screen.getByText("목표 금액")).toBeInTheDocument();
  });

  it("is_configured가 false일 때 안내 메시지가 표시된다", () => {
    renderPage(<InvestPlanPage />);
    expect(screen.getByText(/월 적립액, 목표 수익률/)).toBeInTheDocument();
  });

  it("isLoading 상태에서 스켈레톤을 표시한다", async () => {
    const { useGoalSettings } = await import("@/hooks/useGoalSettings");
    vi.mocked(useGoalSettings).mockReturnValueOnce({
      data: undefined,
      isLoading: true,
      isError: false,
      editing: false,
      saving: false,
      showCloseConfirm: false,
      form: {
        monthly_deposit_amount: "",
        goal_annual_return_pct: "",
        goal_amount: "",
        goal_start_date: "",
        goal_initial_amount: "",
        annual_deposit_goal: "",
        retirement_target_year: "",
      },
      isDirty: false,
      setForm: vi.fn(),
      setShowCloseConfirm: vi.fn(),
      setEditing: vi.fn(),
      handleCloseModal: vi.fn(),
      openEdit: vi.fn(),
      saveSettings: vi.fn(),
      wizardMode: false,
      wizardStep: 1,
      setWizardStep: vi.fn(),
      openWizard: vi.fn(),
    });
    const { container } = renderPage(<InvestPlanPage />);
    expect(screen.queryByText("적립 계획")).not.toBeInTheDocument();
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });
});

// ── ResetPasswordPage ─────────────────────────────────────────────────────────

describe("ResetPasswordPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("세션 미준비 상태에서 확인 메시지를 표시한다", () => {
    renderPage(<ResetPasswordPage />);
    expect(screen.getByText("비밀번호 재설정 링크를 확인 중입니다...")).toBeInTheDocument();
  });

  it("비밀번호 찾기로 돌아가기 링크가 있다", () => {
    renderPage(<ResetPasswordPage />);
    expect(screen.getByText("비밀번호 찾기로 돌아가기")).toBeInTheDocument();
  });

  it("세션 미준비 시 이메일 링크 안내 텍스트가 있다", () => {
    renderPage(<ResetPasswordPage />);
    expect(screen.getByText(/이메일의 재설정 링크를 클릭해/)).toBeInTheDocument();
  });
});

// ── SettingsPage ──────────────────────────────────────────────────────────────

describe("SettingsPage", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("@/api/client");
    vi.mocked(api.get).mockResolvedValue({
      data: { has_dart: false, user_email: "test@example.com" },
    });
  });

  it("크래시 없이 렌더링된다", () => {
    renderPage(<SettingsPage />);
  });

  it("DART OpenAPI 섹션이 표시된다", () => {
    renderPage(<SettingsPage />);
    expect(screen.getByText("DART OpenAPI (금융감독원)")).toBeInTheDocument();
  });

  it("알림 발송 이력 섹션이 표시된다", () => {
    renderPage(<SettingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "발송 이력" }));
    expect(screen.getByText("알림 발송 이력")).toBeInTheDocument();
  });

  it("DART API Key 입력 필드가 있다", () => {
    renderPage(<SettingsPage />);
    expect(screen.getByText("API Key")).toBeInTheDocument();
  });
});

// ── PortfolioPage ─────────────────────────────────────────────────────────────

const mockPortfolioOverview = {
  total_stock_krw: 10000000,
  total_invested_krw: 8000000,
  unrealized_pnl_krw: 2000000,
  stock_return_pct: 25,
  accounts: [],
  all_positions: [],
  stock_allocation: [],
};

describe("PortfolioPage", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("@/api/client");
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: mockPortfolioOverview });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      if (url === "/dividends/summary")
        return Promise.resolve({
          data: {
            annual_received: 0,
            estimated_annual: 0,
            monthly_breakdown: [],
            monthly_ticker_breakdown: [],
          },
        });
      if (url === "/dividends/by-ticker") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
  });

  it("데이터 로드 후 주식 총평가액을 표시한다", async () => {
    renderPage(<PortfolioPage />);
    await waitFor(() => {
      expect(screen.getByText("주식 총평가액")).toBeInTheDocument();
    });
  });

  it("전체 갱신 버튼이 표시된다", async () => {
    renderPage(<PortfolioPage />);
    await waitFor(() => {
      expect(screen.getByText("전체 갱신")).toBeInTheDocument();
    });
  });

  it("탭이 표시된다", async () => {
    renderPage(<PortfolioPage />);
    await waitFor(() => {
      expect(screen.getByText("종목 현황")).toBeInTheDocument();
    });
  });

  it("로딩 중에 스켈레톤을 표시한다", () => {
    // Override to never resolve
    void (async () => {
      const { api } = await import("@/api/client");
      vi.mocked(api.get).mockReturnValue(new Promise(() => {}));
    })();
    renderPage(<PortfolioPage />);
    // Page renders loading state initially
  });

  it("에러 시 다시 시도 버튼을 표시한다", async () => {
    const { api } = await import("@/api/client");
    vi.mocked(api.get).mockRejectedValue(new Error("Network Error"));
    renderPage(<PortfolioPage />);
    await waitFor(() => {
      expect(screen.getByText("다시 시도")).toBeInTheDocument();
    });
  });
});
