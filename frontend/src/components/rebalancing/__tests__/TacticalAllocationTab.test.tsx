import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { TacticalStatus } from "@/api/tactical";

vi.mock("@/api/portfolios", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/portfolios")>();
  return {
    ...actual,
    fetchPortfolios: vi.fn().mockResolvedValue([
      { id: "p1", name: "미국 전술", items: [], base_type: "STOCK_ONLY", sort_order: 0 },
      { id: "p2", name: "배당", items: [], base_type: "STOCK_ONLY", sort_order: 1 },
    ]),
  };
});

vi.mock("@/api/tactical", () => ({
  fetchTacticalStatus: vi.fn(),
  upsertTacticalStrategy: vi.fn(),
  deleteTacticalStrategy: vi.fn(),
  applyTacticalWeights: vi.fn(),
  fetchTacticalBacktest: vi.fn(),
}));

vi.mock("@/api/alerts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/alerts")>();
  return { ...actual, fetchRebalancingAlerts: vi.fn().mockResolvedValue([]) };
});

vi.mock("@/utils/queryInvalidation", () => ({
  invalidateTacticalData: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

import * as alertsApi from "@/api/alerts";
import * as tacticalApi from "@/api/tactical";
import { MemoryRouter } from "react-router-dom";
import TacticalAllocationTab from "@/components/rebalancing/TacticalAllocationTab";

const DEFAULT_TABLE = {
  RISK_ON: { QQQ: 50, SPY: 40, DIA: 0, QLD: 0, SSO: 0, CASH: 10 },
  NEUTRAL: { QQQ: 30, SPY: 40, DIA: 0, QLD: 0, SSO: 0, CASH: 30 },
  RISK_OFF: { QQQ: 10, SPY: 30, DIA: 0, QLD: 0, SSO: 0, CASH: 60 },
};

function makeStatus(overrides: Partial<TacticalStatus> = {}): TacticalStatus {
  return {
    portfolio_id: "p1",
    portfolio_name: "미국 전술",
    enabled: true,
    notify_enabled: true,
    use_macro: true,
    macro_level: "GREEN",
    macro_freshness: "LIVE",
    technicals: {
      QQQ: {
        close: 716.19,
        sma20: 730.0,
        sma60: 720.0,
        sma120: 700.0,
        sma50: 726.17,
        sma200: 674.72,
        rsi14: 40.2,
        macd_hist: -5.08,
        drawdown_pct: -5.7,
        trend: "UP",
        pullback_stage: "SMA60",
      },
      SPY: {
        close: 767.87,
        sma50: 767.24,
        sma200: 722.78,
        rsi14: 48.9,
        macd_hist: -1.16,
        drawdown_pct: -1.4,
        trend: "UP",
      },
      DIA: {
        close: 470.1,
        sma50: 472.3,
        sma200: 455.0,
        rsi14: 45.0,
        macd_hist: -0.8,
        drawdown_pct: -2.1,
        trend: "NEUTRAL",
      },
    },
    observed_regime: "RISK_ON",
    confirmed_regime: "RISK_ON",
    pending_regime: null,
    regime_changed_at: null,
    applied_regime: null,
    reasons: ["매크로 신호: 안정", "SPY 추세: 상승 · QQQ 추세: 상승"],
    regime_weights: DEFAULT_TABLE,
    is_default_weights: true,
    proposed_weights: DEFAULT_TABLE.RISK_ON,
    current_weights: { AAPL: 100 },
    current_groups: {},
    portfolio_compatible: false,
    tilt_shift_pct: 10,
    observed_tilt: "BALANCED",
    confirmed_tilt: "BALANCED",
    tilt_evaluated_on: "2026-10-01",
    tilt_inputs: { real_yield: 1.8, real_yield_change_pp: -0.05, relative_strength_pct: 0.4 },
    tilt_reasons: [
      "미국 10년 실질금리: 1.80% (20거래일 -0.05%p)",
      "QQQ/SPY 상대강도: 50일 평균 대비 +0.4%",
    ],
    dip_shift_pct: 0,
    dip_level: 0,
    pullback_stage: "SMA60",
    dip_deployed_pct: 0,
    dip_reasons: ["QQQ 웅덩이 단계: 60일선 웅덩이"],
    partial_regime: null,
    partial_applied_on: null,
    transition_hints: [],
    ...overrides,
  };
}

function renderTab(onGoToExecution = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <TacticalAllocationTab onGoToExecution={onGoToExecution} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return { onGoToExecution };
}

/** 판정 근거는 기본 접힘(plans/69 P4) — 지표·근거를 보는 테스트는 먼저 펼친다 */
async function openDetails() {
  fireEvent.click(await screen.findByText("판정 근거"));
}

describe("TacticalAllocationTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(alertsApi.fetchRebalancingAlerts).mockResolvedValue([]);
    localStorage.clear(); // 접힘 상태 기억(useCollapsible)이 테스트 사이에 새지 않게
  });

  it("국면 배지·지표·제안 비중과 비호환 경고를 보여준다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus());
    renderTab();

    expect(await screen.findByText("공격")).toBeDefined();
    expect(tacticalApi.fetchTacticalStatus).toHaveBeenCalledWith("p1");
    expect(screen.getByText("기타 종목")).toBeDefined();
    expect(
      screen.getByText(/나스닥100·S&P500·다우존스·나스닥100 2배·S&P500 2배·현금 외 종목이 있어요/),
    ).toBeDefined();
    // 비중표에 DIA가 없으면 비중 비교 행을 숨긴다
    expect(screen.queryByText("다우존스")).toBeNull();
  });

  it("판정 근거엔 근거 문장만 두고, 차트 지표는 진단 탭 시장 상황으로 보낸다 (plans/82)", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus());
    renderTab();
    // 웅덩이 투입폭 0이면 요약 줄은 "사용 안 함"
    expect(await screen.findByText("사용 안 함")).toBeDefined();
    await openDetails();

    expect(await screen.findByText("SPY 추세: 상승 · QQQ 추세: 상승")).toBeDefined();
    expect(screen.getByText("매크로(확정)")).toBeDefined();
    // 지표 행(추세·RSI·이평 이격)은 진단 탭 ChartTrendList가 그린다
    expect(screen.queryByText("추세 상승")).toBeNull();
    expect(screen.queryByText("RSI(14)")).toBeNull();
    const link = screen.getByRole("link", { name: /매크로·차트 지표 자세히 보기/ });
    expect(link.getAttribute("href")).toContain("/rebalancing");
  });

  it("페이지에서 고른 포트폴리오(URL)를 쓰고, 바꾸면 부모에 알린다 (plans/63 P3-3)", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ portfolio_id: "p2" }),
    );
    const onSelectPortfolio = vi.fn();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <TacticalAllocationTab
          onGoToExecution={vi.fn()}
          selectedPortfolioId="p2"
          onSelectPortfolio={onSelectPortfolio}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(tacticalApi.fetchTacticalStatus).toHaveBeenCalledWith("p2"));
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "p1" } });
    expect(onSelectPortfolio).toHaveBeenCalledWith("p1");
  });

  it("목표 조정 탭이 공용 선택기를 그리면 자체 select를 숨긴다 (plans/64 S2)", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ portfolio_id: "p2" }),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <TacticalAllocationTab
          onGoToExecution={vi.fn()}
          selectedPortfolioId="p2"
          onSelectPortfolio={vi.fn()}
          showPortfolioPicker={false}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(tacticalApi.fetchTacticalStatus).toHaveBeenCalledWith("p2"));
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("DIA 제안 비중이 있으면 비교 행을 보여준다", async () => {
    const proposed = { QQQ: 40, SPY: 30, DIA: 20, QLD: 0, SSO: 0, CASH: 10 };
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ proposed_weights: proposed }),
    );
    renderTab();
    expect(await screen.findByText("다우존스")).toBeDefined();
  });

  it("전략이 꺼져 있으면 켜기 버튼으로 알림과 함께 활성화한다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ enabled: false, confirmed_regime: null }),
    );
    vi.mocked(tacticalApi.upsertTacticalStrategy).mockResolvedValue(makeStatus());
    renderTab();

    fireEvent.click(await screen.findByText(/전술 배분 켜기/));
    await waitFor(() =>
      expect(tacticalApi.upsertTacticalStrategy).toHaveBeenCalledWith("p1", {
        notify_enabled: true,
      }),
    );
  });

  it("적용은 확인 모달을 거치고, 성공하면 실행 화면 이동 버튼이 나온다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus());
    vi.mocked(tacticalApi.applyTacticalWeights).mockResolvedValue(makeStatus());
    const { onGoToExecution } = renderTab();

    fireEvent.click(await screen.findByText("제안 비중을 목표 비중으로 적용"));
    expect(tacticalApi.applyTacticalWeights).not.toHaveBeenCalled();
    expect(screen.getByText(/주문은 나가지 않으며/)).toBeDefined();

    // 다른 종목이 섞인 포트폴리오는 분할 적용 버튼이 없다
    expect(screen.queryByText("절반 먼저 적용")).toBeNull();
    fireEvent.click(screen.getByText("한 번에 적용"));
    await waitFor(() => expect(tacticalApi.applyTacticalWeights).toHaveBeenCalledWith("p1", 1));

    fireEvent.click(await screen.findByText("리밸런싱 분석·실행으로 이동"));
    expect(onGoToExecution).toHaveBeenCalledWith("p1");
  });

  it("국면 미확정이면 적용 버튼이 비활성화된다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ confirmed_regime: null, pending_regime: "RISK_OFF" }),
    );
    renderTab();

    const btn = (await screen.findByText("제안 비중을 목표 비중으로 적용")) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(screen.getByText(/방어 전환 확인 중/)).toBeDefined();
  });

  it("나스닥·S&P 틸트 상태와 다음 달 반영 예정 안내를 보여준다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ confirmed_tilt: "FAVOR_SPY", observed_tilt: "FAVOR_QQQ" }),
    );
    renderTab();

    expect(await screen.findByText("S&P500 우위 (10%p 이동)")).toBeDefined();
    await openDetails();
    expect(screen.getByText(/오늘 판단은 나스닥 우위/)).toBeDefined();
    expect(screen.getByText(/미국 10년 실질금리/)).toBeDefined();
  });

  it("틸트 이동폭이 0이면 조절 안 함으로 표시한다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus({ tilt_shift_pct: 0 }));
    renderTab();

    expect(await screen.findByText("조절 안 함")).toBeDefined();
    await openDetails();
    expect(screen.queryByText(/미국 10년 실질금리/)).toBeNull();
  });

  it("알림 토글은 현재 틸트 이동폭을 유지한 채 저장한다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ tilt_shift_pct: 15 }),
    );
    vi.mocked(tacticalApi.upsertTacticalStrategy).mockResolvedValue(makeStatus());
    renderTab();

    fireEvent.click(await screen.findByLabelText("국면 전환 알림"));
    await waitFor(() =>
      expect(tacticalApi.upsertTacticalStrategy).toHaveBeenCalledWith("p1", {
        notify_enabled: false,
        regime_weights: null,
        tilt_shift_pct: 15,
        dip_shift_pct: 0,
        use_macro: true,
      }),
    );
  });

  it("매크로 반영을 끈 전략은 매크로 배지 대신 추세만 쓴다고 알린다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus({ use_macro: false }));
    renderTab();
    await openDetails();
    expect(screen.getByText(/매크로 반영 안 함/)).toBeDefined();
    expect(screen.queryByText("매크로(확정)")).toBeNull();
  });

  it("웅덩이 투입 중이면 서버가 계산한 실제 투입량을 보여준다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ dip_shift_pct: 30, dip_level: 3, dip_deployed_pct: 10 }),
    );
    renderTab();
    expect(await screen.findByText("현금 10%p 투입 중")).toBeDefined();
  });

  it("단계는 진행 중인데 현금이 없으면 투입할 현금 없음으로 표시한다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ dip_shift_pct: 15, dip_level: 2, dip_deployed_pct: 0 }),
    );
    renderTab();
    expect(await screen.findByText("투입할 현금 없음")).toBeDefined();
  });

  it("절반 적용 상태면 나머지 적용만 제안하고 실행 화면으로도 갈 수 있다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({
        portfolio_compatible: true,
        current_weights: { QQQ: 40, SPY: 40, CASH: 20 },
        partial_regime: "RISK_ON",
        partial_applied_on: "2026-10-20",
      }),
    );
    vi.mocked(tacticalApi.applyTacticalWeights).mockResolvedValue(makeStatus());
    renderTab();

    expect(await screen.findByText("절반 적용함 — 나머지를 적용하세요")).toBeDefined();
    expect(screen.getByText(/10\/20 절반 적용/)).toBeDefined();
    expect(screen.getByText("리밸런싱 분석·실행으로 이동")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "나머지 적용" }));
    expect(screen.queryByText("절반 먼저 적용")).toBeNull();
    const buttons = screen.getAllByRole("button", { name: "나머지 적용" });
    fireEvent.click(buttons[buttons.length - 1]!);
    await waitFor(() => expect(tacticalApi.applyTacticalWeights).toHaveBeenCalledWith("p1", 1));
  });

  it("다음 전환 조건과 확정 안내를 최대 2줄 보여준다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({
        transition_hints: [
          { kind: "TO_NEUTRAL", text: "QQQ가 3.9% 더 내려 200일선 아래", distance_pct: -3.9 },
          { kind: "TO_RISK_OFF", text: "매크로 위험이면 방어 후보", distance_pct: null },
          { kind: "TO_RISK_OFF", text: "세 번째 줄", distance_pct: null },
        ],
      }),
    );
    renderTab();
    expect(await screen.findByText("QQQ가 3.9% 더 내려 200일선 아래")).toBeDefined();
    expect(screen.getByText("매크로 위험이면 방어 후보")).toBeDefined();
    expect(screen.queryByText("세 번째 줄")).toBeNull();
    expect(screen.getByText(/다음 거래일에 한 번 더 확인돼야/)).toBeDefined();
  });

  it("이미 적용한 국면이면 할 일 없음과 유지 일수를 보여준다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({
        applied_regime: "RISK_ON",
        current_weights: DEFAULT_TABLE.RISK_ON,
        portfolio_compatible: true,
        regime_changed_at: new Date().toISOString(),
      }),
    );
    renderTab();
    expect(await screen.findByText("할 일 없음 · 공격 국면 유지 1일째")).toBeDefined();
    expect(screen.getByText("1일째")).toBeDefined();
    expect(screen.queryByText("제안 비중을 목표 비중으로 적용")).toBeNull();
  });

  it("전략을 켜지 않았으면 배지에 오늘 관측임을 밝힌다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ enabled: false, confirmed_regime: null }),
    );
    renderTab();
    expect(await screen.findByText("공격 (오늘 관측)")).toBeDefined();
    expect(screen.getByText("켜면 국면이 바뀔 때 알려드려요")).toBeDefined();
  });

  it("전술 자산만 있는 포트폴리오는 절반만 먼저 적용할 수 있다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ portfolio_compatible: true, current_weights: { QQQ: 30, SPY: 40, CASH: 30 } }),
    );
    vi.mocked(tacticalApi.applyTacticalWeights).mockResolvedValue(makeStatus());
    renderTab();

    fireEvent.click(await screen.findByText("제안 비중을 목표 비중으로 적용"));
    fireEvent.click(screen.getByText("절반 먼저 적용"));
    await waitFor(() => expect(tacticalApi.applyTacticalWeights).toHaveBeenCalledWith("p1", 0.5));
    expect(await screen.findByText("리밸런싱 분석·실행으로 이동")).toBeDefined();
  });

  it("지수 그룹 포트폴리오는 그룹 구성을 보조 문구로 보여준다 (plans/76)", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({
        portfolio_compatible: true,
        current_weights: { SPY: 40, CASH: 60 },
        current_groups: {
          SPY: { label: "S&P 500", primary: "VOO", member_count: 2, domestic_alt: "360750" },
        },
      }),
    );
    renderTab();

    expect(await screen.findByText("대표 VOO · 2종목 합산")).toBeDefined();
    // 나스닥 그룹은 아직 없음 — 적용 시 묶인다는 안내
    expect(screen.getByText("적용하면 같은 지수 보유 종목을 묶어요")).toBeDefined();
    expect(screen.queryByText("기타 종목")).toBeNull();
  });

  it("전략이 꺼져 있으면 비중표 편집을 보여주지 않는다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ enabled: false, confirmed_regime: null }),
    );
    renderTab();
    await screen.findByText(/전술 배분 켜기/);
    expect(screen.queryByText("비중표 편집")).toBeNull();
  });

  it("포트폴리오를 바꾸면 방금 적용한 상태를 이어받지 않는다 (plans/77 C1)", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockImplementation(async (id: string) =>
      makeStatus({ portfolio_id: id, portfolio_name: id }),
    );
    vi.mocked(tacticalApi.applyTacticalWeights).mockResolvedValue(makeStatus());
    renderTab();
    const select = async (id: string) => {
      fireEvent.change(await screen.findByRole("combobox"), { target: { value: id } });
      await waitFor(() => expect(tacticalApi.fetchTacticalStatus).toHaveBeenCalledWith(id));
      await screen.findByText("제안 비중을 목표 비중으로 적용");
    };
    // p2를 한 번 열어 캐시에 둔다 — 캐시된 포트폴리오로 돌아갈 때는 로딩 없이 바로 그려져 상태가 이어졌다
    await screen.findByText("제안 비중을 목표 비중으로 적용");
    await select("p2");
    await select("p1");

    fireEvent.click(screen.getByText("제안 비중을 목표 비중으로 적용"));
    fireEvent.click(screen.getByText("한 번에 적용"));
    await screen.findByText("리밸런싱 분석·실행으로 이동");

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "p2" } });
    expect(await screen.findByText("제안 비중을 목표 비중으로 적용")).toBeDefined();
    expect(screen.queryByText("리밸런싱 분석·실행으로 이동")).toBeNull();
  });

  it("포트폴리오를 바꾸면 그 포트폴리오로 다시 조회한다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus());
    renderTab();
    await screen.findByText("공격");

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "p2" } });
    await waitFor(() => expect(tacticalApi.fetchTacticalStatus).toHaveBeenCalledWith("p2"));
  });
  function dcaAlert(market_condition_mode: alertsApi.MarketConditionMode) {
    return {
      portfolio_id: "p1",
      is_active: true,
      mode: "AUTO",
      strategy: "BUY_ONLY",
      market_condition_mode,
      threshold_pct: 0.5,
    } as unknown as alertsApi.RebalancingAlert;
  }

  it("적립 자동매수 포트폴리오면 비중 적용 대신 전술 연동을 권하는 안내를 보여준다", async () => {
    vi.mocked(alertsApi.fetchRebalancingAlerts).mockResolvedValue([dcaAlert("DISABLED")]);
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus());
    renderTab();
    expect(await screen.findByText("적립 자동매수 중인 포트폴리오예요")).toBeDefined();
    const link = screen.getByText("자동매수 설정 열기").closest("a");
    expect(link?.getAttribute("href")).toContain("openAlert=1");
  });

  it("전술 연동 중이면 적립 보조 모드 문구를 보여주고 방어 국면엔 매수 보류를 알린다", async () => {
    vi.mocked(alertsApi.fetchRebalancingAlerts).mockResolvedValue([dcaAlert("TACTICAL")]);
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ confirmed_regime: "RISK_OFF", observed_regime: "RISK_OFF" }),
    );
    renderTab();
    expect(await screen.findByText(/이번 적립 매수는 보류돼요/)).toBeDefined();
    expect(screen.getByText(/적립 보조 모드/)).toBeDefined();
    expect(screen.queryByText("적립 자동매수 중인 포트폴리오예요")).toBeNull();
  });

  it("전술 연동 중 공격 국면이면 적립 정상 진행으로 안내한다", async () => {
    vi.mocked(alertsApi.fetchRebalancingAlerts).mockResolvedValue([dcaAlert("TACTICAL")]);
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus());
    renderTab();
    expect(await screen.findByText(/적립 매수 정상 진행 · 공격 국면/)).toBeDefined();
  });

  it("전술 연동 중에 전술 배분을 끄면 연동 해제 안내와 함께 끈다", async () => {
    vi.mocked(alertsApi.fetchRebalancingAlerts).mockResolvedValue([dcaAlert("TACTICAL")]);
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus());
    vi.mocked(tacticalApi.deleteTacticalStrategy).mockResolvedValue(undefined as never);
    renderTab();
    await screen.findByText(/적립 보조 모드/);
    fireEvent.click(screen.getByText("전술 배분 끄기"));
    const { toast } = await import("@/utils/toast");
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(expect.stringContaining("일반 모드로 바뀌었어요"), "info"),
    );
  });

  it("연동 안내가 안 뜨는 경우에도 끄면 알림 캐시를 비운다", async () => {
    // 적립식 중 하나만 TACTICAL이면 linked=false지만 서버는 그 TACTICAL 알림을 DISABLED로 바꾼다 (plans/101 A1)
    vi.mocked(alertsApi.fetchRebalancingAlerts).mockResolvedValue([
      dcaAlert("TACTICAL"),
      { ...dcaAlert("DISABLED"), id: "a2", account_id: "acc2" },
    ]);
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus());
    vi.mocked(tacticalApi.deleteTacticalStrategy).mockResolvedValue(undefined as never);
    renderTab();
    fireEvent.click(await screen.findByText("전술 배분 끄기"));
    const { invalidateTacticalData } = await import("@/utils/queryInvalidation");
    await waitFor(() =>
      expect(invalidateTacticalData).toHaveBeenCalledWith(expect.anything(), { alertsReset: true }),
    );
  });
});
