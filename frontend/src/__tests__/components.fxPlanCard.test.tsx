import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { FxPlanData } from "@/api/invest";
import type { ExchangeRateAlert } from "@/api/alerts";

vi.mock("@/api/invest", () => ({ fetchFxPlan: vi.fn() }));
vi.mock("@/api/alerts", () => ({
  fetchExchangeRateAlerts: vi.fn(),
  createExchangeRateAlert: vi.fn(),
}));
vi.mock("@/utils/queryInvalidation", () => ({ invalidateAlertData: vi.fn() }));
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

import { fetchFxPlan } from "@/api/invest";
import { createExchangeRateAlert, fetchExchangeRateAlerts } from "@/api/alerts";
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

describe("FxPlanCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([]);
    vi.mocked(createExchangeRateAlert).mockResolvedValue(alert(0));
  });

  it("위치·필요 달러·구간을 보여준다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    renderWithProviders(<FxPlanCard flat />);
    expect(await screen.findByText(/1년 중 중간/)).toBeInTheDocument();
    expect(screen.getByText(/환율 예측이 아닙니다/)).toBeInTheDocument();
    expect(screen.getByText(/\$1,700 필요/)).toBeInTheDocument();
    expect(screen.getByText("1,380원 이하")).toBeInTheDocument();
    expect(fetchFxPlan).toHaveBeenCalledWith(3, null);
  });

  it("기간을 바꾸면 그 기간으로 다시 조회한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    renderWithProviders(<FxPlanCard flat />);
    fireEvent.click(await screen.findByRole("tab", { name: "6개월" }));
    await waitFor(() => expect(fetchFxPlan).toHaveBeenCalledWith(6, null));
  });

  it("이미 등록된 목표 환율은 건너뛰고 나머지만 알림 등록한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([
      alert(1380),
      alert(1360, { is_active: false }),
    ]);
    renderWithProviders(<FxPlanCard flat />);
    expect(await screen.findByText("알림 등록됨")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "목표 환율 알림 등록" }));
    await waitFor(() => expect(createExchangeRateAlert).toHaveBeenCalledTimes(1));
    expect(createExchangeRateAlert).toHaveBeenCalledWith(1360, "BELOW", 1);
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(expect.stringContaining("1건"), "success"),
    );
  });

  it("모든 목표가 등록돼 있으면 버튼이 비활성화된다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue(plan);
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([alert(1380), alert(1360)]);
    renderWithProviders(<FxPlanCard flat />);
    expect(await screen.findByRole("button", { name: "목표 환율 알림 등록됨" })).toBeDisabled();
  });

  it("월 적립액 미설정이면 설정 버튼을 보여준다", async () => {
    const onEditGoal = vi.fn();
    vi.mocked(fetchFxPlan).mockResolvedValue({ ...plan, status: "NO_DEPOSIT_GOAL", tranches: [] });
    renderWithProviders(<FxPlanCard flat onEditGoal={onEditGoal} />);
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
    renderWithProviders(<FxPlanCard flat />);
    expect(await screen.findByText(/해외 종목이 들어 있는 포트폴리오가 없어/)).toBeInTheDocument();
  });

  it("이미 충분하면 구간 없이 안내한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({
      ...plan,
      status: "SUFFICIENT",
      need_usd: 0,
      tranches: [],
    });
    renderWithProviders(<FxPlanCard flat />);
    expect(await screen.findByText(/이미 보유한 달러로 3개월치/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /알림 등록/ })).not.toBeInTheDocument();
  });

  it("시세 없이도 계획을 보여주고, 조회 실패 시 안내한다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValueOnce({ ...plan, position: null });
    const { unmount } = renderWithProviders(<FxPlanCard flat />);
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
    renderWithProviders(<FxPlanCard flat />);
    fireEvent.change(await screen.findByLabelText("포트폴리오 선택"), { target: { value: "p2" } });
    await waitFor(() => expect(fetchFxPlan).toHaveBeenCalledWith(3, "p2"));
  });

  it("실시간 환율이 없으면 최근 종가 기준임을 알린다", async () => {
    vi.mocked(fetchFxPlan).mockResolvedValue({ ...plan, rate_is_live: false });
    renderWithProviders(<FxPlanCard flat />);
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
    renderWithProviders(<FxPlanCard flat />);
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
    renderWithProviders(<FxPlanCard flat />);
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
    renderWithProviders(<FxPlanCard flat />);
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
    renderWithProviders(<FxPlanCard flat />);
    expect(await screen.findByText(/환율을 불러오지 못해 필요한 달러를/)).toBeInTheDocument();
    expect(screen.queryByText(/필요$/)).not.toBeInTheDocument();
  });
});
