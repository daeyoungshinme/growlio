import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders as renderBase } from "@/test/renderWithProviders";

// "환율 알림 관리" 링크가 있어 라우터 안에서 렌더한다
const renderWithProviders = (ui: ReactNode) => renderBase(<MemoryRouter>{ui}</MemoryRouter>);
import type { FxPlanData } from "@/api/invest";
import type { ExchangeRateAlert } from "@/api/alerts";

// 카드 아래 추가 환전 섹션(plans/123)은 components.fxExtraNeedsSection.test.tsx에서 본다 — 여기선 빈 목록
vi.mock("@/api/invest", () => ({
  fetchFxPlan: vi.fn(),
  syncFxPlanAlerts: vi.fn(),
  fetchFxExtraNeeds: vi.fn(() => Promise.resolve({ rate: null, rate_is_live: true, needs: [] })),
  createFxExtraNeed: vi.fn(),
  updateFxExtraNeed: vi.fn(),
  deleteFxExtraNeed: vi.fn(),
  syncFxExtraNeedAlerts: vi.fn(),
}));
vi.mock("@/api/alerts", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/alerts")>()),
  fetchExchangeRateAlerts: vi.fn(),
}));
vi.mock("@/api/assets", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/assets")>()),
  fetchAccounts: vi.fn(() => Promise.resolve([])),
  syncAccount: vi.fn(() => Promise.resolve({})),
}));
vi.mock("@/utils/queryInvalidation", () => ({
  invalidateAlertData: vi.fn(),
  invalidateFxExtraNeedData: vi.fn(),
  invalidateSyncData: vi.fn(() => Promise.resolve()),
}));
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

import { fetchFxExtraNeeds, fetchFxPlan, syncFxPlanAlerts } from "@/api/invest";
import { fetchExchangeRateAlerts } from "@/api/alerts";
import { fetchAccounts, syncAccount, type AssetAccount } from "@/api/assets";
import { invalidateSyncData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import FxPlanCard from "@/components/invest/FxPlanCard";
import { QUERY_KEYS } from "@/constants/queryKeys";

const position: NonNullable<FxPlanData["position"]> = {
  rate: 1400,
  low_1y: 1300,
  high_1y: 1500,
  percentile_1y: 50,
  ma20: 1390,
  ma60: 1380,
  deviation_ma20_pct: 0.72,
  deviation_ma60_pct: 1.45,
  sigma_1m: 40,
  range_1m_low: 1360,
  range_1m_high: 1440,
  zone: "NEUTRAL",
};

const plan: FxPlanData = {
  position,
  rate_is_live: true,
  status: "OK",
  portfolio_id: "p1",
  portfolio_name: "해외 적립",
  portfolio_options: [{ id: "p1", name: "해외 적립" }],
  months: 3,
  overseas_weight_pct: 60,
  monthly_deposit_krw: 1_400_000,
  monthly_need_usd: 600,
  held_usd: 100,
  need_usd: 1700,
  tranches: [
    { label: "지금", target_rate: null, usd: 578, krw_estimate: 809_200 },
    { label: "1,380원 이하", target_rate: 1380, usd: 561, krw_estimate: 774_180 },
    { label: "1,360원 이하", target_rate: 1360, usd: 561, krw_estimate: 762_960 },
  ],
};

const alert = (target_rate: number, over: Partial<ExchangeRateAlert> = {}): ExchangeRateAlert => ({
  id: `a-${target_rate}`,
  target_rate,
  direction: "BELOW",
  is_active: true,
  max_trigger_count: 1,
  trigger_count: 0,
  triggered_at: null,
  created_at: "2026-10-30T00:00:00Z",
  ...over,
});

/** 이 계획(p1)으로 만든 구간 알림 */
const planAlert = (target_rate: number, planned_usd = 561, over: Partial<ExchangeRateAlert> = {}) =>
  alert(target_rate, { source: "FX_PLAN", planned_usd, portfolio_id: "p1", ...over });

describe("FxPlanCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([]);
    vi.mocked(syncFxPlanAlerts).mockResolvedValue({
      created: 2,
      updated: 0,
      removed: 0,
      skipped_manual: 0,
      skipped_shared: 0,
    });
  });

  it("위치·필요 달러·구간을 보여준다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/1년 중 중간/)).toBeInTheDocument();
    expect(screen.getByText(/환율 예측이 아닙니다/)).toBeInTheDocument();
    expect(screen.getByText(/\$1,700 필요/)).toBeInTheDocument();
    expect(screen.getByText("1,380원 이하")).toBeInTheDocument();
    expect(fetchFxPlan).toHaveBeenCalledWith(3, null);
  });

  it("정액 적립이면 적립 금액의 해외 몫 기준임을 보여준다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({
      ...plan,
      deposit_source: "DCA_AMOUNT",
      monthly_deposit_krw: 1_000_000,
    });
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/정액 적립 월 100만원의 해외 몫/)).toBeInTheDocument();
  });

  it("보유 달러는 동기화 기준이고 기준 시각을 함께 보여준다", async () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 3_600_000).toISOString();
    vi.mocked(fetchFxPlan).mockResolvedValue({ ...plan, held_usd_synced_at: twoHoursAgo });
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/\(동기화 기준 · 2시간 전\)/)).toBeInTheDocument();
    expect(screen.getByText(/해외 비중 60%/)).toBeInTheDocument();
  });

  it("달러 예수금 새로 받기는 동기화 가능한 증권 계좌만 동기화한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    vi.mocked(fetchAccounts).mockResolvedValue([
      { id: "kis", asset_type: "STOCK_KIS", data_source: "KIS_API" },
      { id: "meritz", asset_type: "STOCK_OTHER", data_source: "MANUAL" },
      { id: "bank", asset_type: "BANK", data_source: "MANUAL" },
    ] as unknown as AssetAccount[]);
    renderWithProviders(<FxPlanCard />);
    fireEvent.click(await screen.findByRole("button", { name: "달러 예수금 새로 받기" }));
    await waitFor(() => expect(invalidateSyncData).toHaveBeenCalled());
    expect(syncAccount).toHaveBeenCalledTimes(1);
    expect(vi.mocked(syncAccount).mock.calls[0]?.[0]).toBe("kis");
  });

  it("새로 받기가 일부만 실패하면 몇 개가 실패했는지, 전부 실패하면 다시 시도를 안내한다 — plans/128 A2", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    vi.mocked(fetchAccounts).mockResolvedValue([
      { id: "kis", asset_type: "STOCK_KIS", data_source: "KIS_API" },
      { id: "kiwoom", asset_type: "STOCK_KIWOOM", data_source: "KIWOOM_API" },
    ] as unknown as AssetAccount[]);
    vi.mocked(syncAccount)
      .mockResolvedValueOnce({} as never)
      .mockRejectedValueOnce(new Error("x"));
    renderWithProviders(<FxPlanCard />);
    const button = await screen.findByRole("button", { name: "달러 예수금 새로 받기" });
    fireEvent.click(button);
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        "계좌 2개 중 1개의 달러 예수금을 받지 못했습니다",
        "error",
      ),
    );

    vi.mocked(syncAccount).mockRejectedValue(new Error("x"));
    fireEvent.click(await screen.findByRole("button", { name: "달러 예수금 새로 받기" }));
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        "달러 예수금을 받지 못했습니다. 잠시 후 다시 시도해 주세요",
        "error",
      ),
    );
  });

  it("재조회가 실패해도 받아 둔 계획을 계속 보여 준다 — plans/128 A3", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.mocked(fetchFxPlan).mockResolvedValueOnce(plan).mockRejectedValue(new Error("503"));
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <FxPlanCard />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByText(/\$1,700 필요/);
    await qc.invalidateQueries({ queryKey: QUERY_KEYS.fxPlanBase });
    await waitFor(() => expect(vi.mocked(fetchFxPlan).mock.calls.length).toBeGreaterThan(1));
    expect(screen.getByText(/\$1,700 필요/)).toBeInTheDocument();
    expect(screen.queryByText(/환전 계획을 불러오지 못했습니다/)).toBeNull();
  });

  it("계획이 다시 받아지면 다른 기간도 다시 받아 둔다 — plans/128 A4", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <FxPlanCard />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(fetchFxPlan).toHaveBeenCalledTimes(3));
    await qc.invalidateQueries({ queryKey: QUERY_KEYS.fxPlanBase });
    // 화면의 3개월 + 무효화돼 stale이 된 1·6개월
    await waitFor(() => expect(fetchFxPlan).toHaveBeenCalledTimes(6));
  });

  it("동기화할 증권 계좌가 없으면 새로 받기 버튼을 숨긴다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    vi.mocked(fetchAccounts).mockResolvedValue([]);
    renderWithProviders(<FxPlanCard />);
    await screen.findByText(/\$1,700 필요/);
    expect(screen.queryByRole("button", { name: "달러 예수금 새로 받기" })).toBeNull();
  });

  it("보유 달러를 계좌별로 보여주고 수기 계좌가 섞이면 직접 입력 포함으로 표시한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({
      ...plan,
      held_usd_accounts: [
        { account_id: "m", name: "메리츠", usd: 1200, source: "MANUAL" },
        { account_id: "k", name: "한국투자", usd: 333, source: "SYNCED" },
      ],
    });
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/\(직접 입력 포함\)/)).toBeInTheDocument();
    expect(
      screen.getByText("보유 달러: 메리츠 $1,200(직접 입력) · 한국투자 $333(동기화 기준)"),
    ).toBeInTheDocument();
  });

  it("환전 대기 중인 매수가 있으면 지금 환전할 금액과 이력 링크를 보여준다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({ ...plan, waiting_fx_usd: 350 });
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/\$350를 지금/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "대기 중인 매수 보기" });
    expect(decodeURIComponent(link.getAttribute("href") ?? "")).toContain("rtab=이력");
  });

  it("환전 대기가 없으면 안내를 보이지 않는다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    renderWithProviders(<FxPlanCard />);
    await screen.findByText(/\$1,700 필요/);
    expect(screen.queryByRole("link", { name: "대기 중인 매수 보기" })).toBeNull();
  });

  it("계획이 나오면 다른 기간도 미리 받아 둔다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    renderWithProviders(<FxPlanCard />);
    await screen.findByText(/\$1,700 필요/);
    await waitFor(() => expect(fetchFxPlan).toHaveBeenCalledWith(1, null));
    expect(fetchFxPlan).toHaveBeenCalledWith(6, null);
  });

  it("계획이 없는 상태면 다른 기간을 미리 받지 않는다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({ ...plan, status: "NO_DEPOSIT_GOAL", tranches: [] });
    renderWithProviders(<FxPlanCard />);
    await screen.findByText(/월 적립액을 설정하면/);
    expect(fetchFxPlan).toHaveBeenCalledTimes(1);
  });

  it("환전 계획을 기다리지 않고 추가 환전 항목을 함께 조회한다", async () => {
    vi.mocked(fetchFxPlan).mockReturnValue(new Promise(() => {}));
    renderWithProviders(<FxPlanCard />);
    await waitFor(() => expect(fetchFxExtraNeeds).toHaveBeenCalled());
  });

  it("기간을 바꾸면 그 기간으로 다시 조회한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    renderWithProviders(<FxPlanCard />);
    fireEvent.click(await screen.findByRole("tab", { name: "6개월" }));
    await waitFor(() => expect(fetchFxPlan).toHaveBeenCalledWith(6, null));
  });

  it("다른 기간 계획을 받는 동안(이전 계획 표시 중) 알림 등록을 막는다 — plans/126 A3", async () => {
    vi.mocked(fetchFxPlan)
      .mockResolvedValueOnce(plan)
      .mockReturnValue(new Promise(() => {}));
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByRole("button", { name: "목표 환율 알림 등록" })).toBeEnabled();
    fireEvent.click(screen.getByRole("tab", { name: "6개월" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "목표 환율 알림 등록" })).toBeDisabled(),
    );
  });

  it("구간 목표와 금액을 한 번에 맞춰 등록한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    renderWithProviders(<FxPlanCard />);
    fireEvent.click(await screen.findByRole("button", { name: "목표 환율 알림 등록" }));
    await waitFor(() =>
      expect(syncFxPlanAlerts).toHaveBeenCalledWith("p1", [
        { target_rate: 1380, usd: 561 },
        { target_rate: 1360, usd: 561 },
      ]),
    );
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith("목표 환율 알림 2건을 맞췄습니다", "success"),
    );
  });

  it("직접 등록한 같은 목표 알림은 표시만 하고 서버가 건너뛴다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([alert(1380), planAlert(1360)]);
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText("직접 등록한 알림 있음")).toBeInTheDocument();
    expect(screen.getByText("알림 등록됨")).toBeInTheDocument();
    // 직접 등록 1380 + 계획 1360(금액 일치) → 맞춰진 상태
    expect(screen.getByRole("button", { name: "목표 환율 알림 등록됨" })).toBeDisabled();
  });

  it("계획 목표가 바뀌면 새 계획으로 바꾸기를 제안한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([planAlert(1380), planAlert(1350)]);
    renderWithProviders(<FxPlanCard />);
    fireEvent.click(await screen.findByRole("button", { name: "알림을 새 계획으로 바꾸기" }));
    expect(screen.getByText(/새 목표로 교체됩니다/)).toBeInTheDocument();
    await waitFor(() => expect(syncFxPlanAlerts).toHaveBeenCalledTimes(1));
  });

  it("금액만 달라져도 다시 맞추도록 한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([planAlert(1380, 300), planAlert(1360)]);
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByRole("button", { name: "알림을 새 계획으로 바꾸기" })).toBeEnabled();
  });

  it("실시간 재계산으로 몇 달러 흔들린 것은 맞춰진 상태로 본다(plans/122 C3)", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([
      planAlert(1380, 570),
      planAlert(1360, 552),
    ]);
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByRole("button", { name: "목표 환율 알림 등록됨" })).toBeDisabled();
    expect(screen.queryByText(/새 목표로 교체됩니다/)).toBeNull();
  });

  it("목표 구간이 없어져도 옛 계획 알림을 해제할 수 있다(plans/122 C2)", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({
      ...plan,
      position: null,
      tranches: [{ label: "지금", target_rate: null, usd: 1700, krw_estimate: 2_380_000 }],
    });
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([planAlert(1380)]);
    renderWithProviders(<FxPlanCard />);
    fireEvent.click(
      await screen.findByRole("button", { name: "이 계획으로 등록한 알림 1건 해제" }),
    );
    await waitFor(() => expect(syncFxPlanAlerts).toHaveBeenCalledWith("p1", []));
  });

  it("월 적립액이 없어져도 옛 계획 알림을 해제할 수 있다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({ ...plan, status: "NO_DEPOSIT_GOAL", tranches: [] });
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([planAlert(1380)]);
    renderWithProviders(<FxPlanCard onEditGoal={vi.fn()} />);
    expect(
      await screen.findByRole("button", { name: "이 계획으로 등록한 알림 1건 해제" }),
    ).toBeEnabled();
  });

  it("다른 포트폴리오·발동된 계획 알림은 이 계획의 등록으로 보지 않는다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([
      planAlert(1380, 561, { portfolio_id: "p2" }),
      planAlert(1360, 561, { triggered_at: "2026-11-01T00:00:00Z" }),
    ]);
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByRole("button", { name: "목표 환율 알림 등록" })).toBeEnabled();
    expect(screen.queryByText("알림 등록됨")).toBeNull();
  });

  it("달러가 충분해지면 이 계획의 알림을 해제할 수 있다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({
      ...plan,
      status: "SUFFICIENT",
      need_usd: 0,
      tranches: [],
    });
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([planAlert(1380)]);
    vi.mocked(syncFxPlanAlerts).mockResolvedValue({
      created: 0,
      updated: 0,
      removed: 1,
      skipped_manual: 0,
      skipped_shared: 0,
    });
    renderWithProviders(<FxPlanCard />);
    fireEvent.click(
      await screen.findByRole("button", { name: "이 계획으로 등록한 알림 1건 해제" }),
    );
    await waitFor(() => expect(syncFxPlanAlerts).toHaveBeenCalledWith("p1", []));
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith("환전 계획 알림 1건을 해제했습니다", "success"),
    );
  });

  it("알림을 불러오지 못하면 전부 미등록으로 보고 중복 등록하지 않는다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    vi.mocked(fetchExchangeRateAlerts).mockRejectedValue(new Error("down"));
    renderWithProviders(<FxPlanCard />);

    await waitFor(() => expect(fetchExchangeRateAlerts).toHaveBeenCalled());
    // "등록됨"으로 보이면 등록하지 않은 알림을 등록한 줄 안다
    expect(await screen.findByRole("button", { name: "알림 목록 확인 중" })).toBeDisabled();
  });

  it("모든 목표가 등록돼 있으면 버튼이 비활성화된다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([planAlert(1380), planAlert(1360)]);
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByRole("button", { name: "목표 환율 알림 등록됨" })).toBeDisabled();
    // 등록한 알림은 설정 › 알림 설정 › 환율 알림에서 관리
    const link = screen.getByRole("link", { name: "환율 알림 관리 →" });
    expect(decodeURIComponent(link.getAttribute("href") ?? "")).toBe(
      "/settings/notifications?atab=환율 알림",
    );
  });

  it("등록한 목표 환율 알림이 없으면 관리 링크를 보이지 않는다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByRole("button", { name: "목표 환율 알림 등록" })).toBeEnabled();
    expect(screen.queryByRole("link", { name: "환율 알림 관리 →" })).toBeNull();
  });

  it("월 적립액 미설정이면 설정 버튼을 보여준다", async () => {
    const onEditGoal = vi.fn();
    vi.mocked(fetchFxPlan).mockResolvedValue({ ...plan, status: "NO_DEPOSIT_GOAL", tranches: [] });
    renderWithProviders(<FxPlanCard onEditGoal={onEditGoal} />);
    fireEvent.click(await screen.findByRole("button", { name: "월 적립액 설정" }));
    expect(onEditGoal).toHaveBeenCalled();
  });

  it("해외 포트폴리오가 없으면 계획 대신 안내한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({
      ...plan,
      status: "NO_OVERSEAS",
      portfolio_options: [],
      tranches: [],
    });
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/해외 종목이 들어 있는 포트폴리오가 없어/)).toBeInTheDocument();
  });

  it("이미 충분하면 구간 없이 안내한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({
      ...plan,
      status: "SUFFICIENT",
      need_usd: 0,
      tranches: [],
    });
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/이미 보유한 달러로 3개월치/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /알림 등록/ })).not.toBeInTheDocument();
  });

  it("시세 없이도 계획을 보여주고, 조회 실패 시 안내한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValueOnce({ ...plan, position: null });
    const { unmount } = renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/위치 판단 없이/)).toBeInTheDocument();
    unmount();
    vi.mocked(fetchFxPlan).mockRejectedValueOnce(new Error("x"));
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/환전 계획을 불러오지 못했습니다/)).toBeInTheDocument();
  });

  it("해외 포트폴리오가 둘 이상이면 선택기로 바꿀 수 있다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({
      ...plan,
      portfolio_options: [
        { id: "p1", name: "해외 적립" },
        { id: "p2", name: "연금" },
      ],
    });
    renderWithProviders(<FxPlanCard />);
    fireEvent.change(await screen.findByLabelText("포트폴리오 선택"), { target: { value: "p2" } });
    await waitFor(() => expect(fetchFxPlan).toHaveBeenCalledWith(3, "p2"));
  });

  it("실시간 환율이 없으면 최근 종가 기준임을 알린다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({ ...plan, rate_is_live: false });
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/최근 종가 기준/)).toBeInTheDocument();
  });

  it("고른 포트폴리오 조회가 실패하면 자동 선택으로 되돌린다", async () => {
    const options = [
      { id: "p1", name: "해외 적립" },
      { id: "p2", name: "연금" },
    ];
    vi.mocked(fetchFxPlan).mockImplementation((_months, portfolioId) =>
      portfolioId === "p2"
        ? Promise.reject({ response: { status: 404 } })
        : Promise.resolve({ ...plan, portfolio_options: options }),
    );
    renderWithProviders(<FxPlanCard />);
    fireEvent.change(await screen.findByLabelText("포트폴리오 선택"), { target: { value: "p2" } });
    await waitFor(() => expect(fetchFxPlan).toHaveBeenCalledWith(3, "p2"));
    expect(await screen.findByLabelText("포트폴리오 선택")).toHaveValue("p1");
    expect(screen.queryByText(/환전 계획을 불러오지 못했습니다/)).not.toBeInTheDocument();
  });

  it("일시적 오류(5xx)에는 고른 포트폴리오를 지우지 않는다", async () => {
    const options = [
      { id: "p1", name: "해외 적립" },
      { id: "p2", name: "연금" },
    ];
    vi.mocked(fetchFxPlan).mockImplementation((_months, portfolioId) =>
      portfolioId === "p2"
        ? Promise.reject({ response: { status: 503 } })
        : Promise.resolve({ ...plan, portfolio_options: options }),
    );
    renderWithProviders(<FxPlanCard />);
    fireEvent.change(await screen.findByLabelText("포트폴리오 선택"), { target: { value: "p2" } });
    expect(await screen.findByText(/환전 계획을 불러오지 못했습니다/)).toBeInTheDocument();
    // 다른 기간 프리페치(plans/124 D)는 빼고 — 자동 선택(null)으로 되돌아가 3개월을 다시 받지 않았다
    expect(
      vi.mocked(fetchFxPlan).mock.calls.filter(([m, pid]) => m === 3 && pid === null),
    ).toHaveLength(1);
  });

  it("고른 포트폴리오에 해외 종목이 없어져도 선택기로 다른 후보를 고를 수 있다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({
      ...plan,
      status: "NO_OVERSEAS",
      portfolio_id: "p2",
      portfolio_name: "연금",
      tranches: [],
    });
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/선택한 포트폴리오에 해외 종목이 없습니다/)).toBeInTheDocument();
    const picker = screen.getByLabelText("포트폴리오 선택");
    expect(picker).toHaveValue("p2");
    fireEvent.change(picker, { target: { value: "p1" } });
    await waitFor(() => expect(fetchFxPlan).toHaveBeenCalledWith(3, "p1"));
  });

  it("환율을 못 받으면 달러 계산 대신 안내한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({
      ...plan,
      position: null,
      rate_is_live: false,
      status: "NO_RATE",
      tranches: [],
    });
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/환율을 불러오지 못해 필요한 달러를/)).toBeInTheDocument();
    expect(screen.queryByText(/필요$/)).not.toBeInTheDocument();
  });
});

describe("FxPlanCard — 추가 환전 보관 달러 제외(plans/123 후속)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([]);
  });

  it("보유 달러에서 뺀 추가 환전 달러를 산식과 계좌별 내역에 보여준다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({
      ...plan,
      held_usd: 700,
      reserved_usd: 500,
      held_usd_accounts: [
        { account_id: "m1", name: "메리츠", usd: 700, source: "MANUAL", reserved_usd: 500 },
      ],
    });
    renderWithProviders(<FxPlanCard />);
    // 산식과 계좌별 내역 두 곳에 보인다
    const shown = await screen.findAllByText(/추가 환전 \$500 제외/);
    expect(shown).toHaveLength(2);
    expect(shown[1]).toHaveTextContent("메리츠 $700(직접 입력, 추가 환전 $500 제외)");
  });
});
