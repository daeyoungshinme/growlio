import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
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
vi.mock("@/utils/queryInvalidation", () => ({
  invalidateAlertData: vi.fn(),
  invalidateFxExtraNeedData: vi.fn(),
}));
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

import { fetchFxPlan, syncFxPlanAlerts } from "@/api/invest";
import { fetchExchangeRateAlerts } from "@/api/alerts";
import { toast } from "@/utils/toast";
import FxPlanCard from "@/components/invest/FxPlanCard";

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
      held_usd_is_live: true,
    });
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/정액 적립 월 100만원의 해외 몫/)).toBeInTheDocument();
    expect(screen.getByText(/\(실시간\)/)).toBeInTheDocument();
  });

  it("실시간 달러를 못 읽었으면 동기화 기준임을 보여준다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({ ...plan, held_usd_is_live: false });
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/\(동기화 기준\)/)).toBeInTheDocument();
    expect(screen.getByText(/해외 비중 60%/)).toBeInTheDocument();
  });

  it("보유 달러를 계좌별로 보여주고 수기 계좌가 섞이면 직접 입력 포함으로 표시한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({
      ...plan,
      held_usd_is_live: false,
      held_usd_accounts: [
        { account_id: "m", name: "메리츠", usd: 1200, source: "MANUAL" },
        { account_id: "k", name: "한국투자", usd: 333, source: "LIVE" },
      ],
    });
    renderWithProviders(<FxPlanCard />);
    expect(await screen.findByText(/\(직접 입력 포함\)/)).toBeInTheDocument();
    expect(
      screen.getByText("보유 달러: 메리츠 $1,200(직접 입력) · 한국투자 $333(실시간)"),
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

  it("기간을 바꾸면 그 기간으로 다시 조회한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    renderWithProviders(<FxPlanCard />);
    fireEvent.click(await screen.findByRole("tab", { name: "6개월" }));
    await waitFor(() => expect(fetchFxPlan).toHaveBeenCalledWith(6, null));
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
    expect(vi.mocked(fetchFxPlan).mock.calls.filter(([, pid]) => pid === null)).toHaveLength(1);
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
