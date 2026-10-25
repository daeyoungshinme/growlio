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

vi.mock("@/utils/queryInvalidation", () => ({
  invalidateTacticalData: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

import * as tacticalApi from "@/api/tactical";
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
    <QueryClientProvider client={qc}>
      <TacticalAllocationTab onGoToExecution={onGoToExecution} />
    </QueryClientProvider>,
  );
  return { onGoToExecution };
}

/** 판정 근거·차트 지표는 기본 접힘(plans/69 P4) — 지표·근거를 보는 테스트는 먼저 펼친다 */
async function openDetails() {
  fireEvent.click(await screen.findByText("판정 근거·차트 지표"));
}

describe("TacticalAllocationTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear(); // 접힘 상태 기억(useCollapsible)이 테스트 사이에 새지 않게
  });

  it("국면 배지·지표·제안 비중과 비호환 경고를 보여준다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus());
    renderTab();

    expect(await screen.findByText("공격")).toBeDefined();
    expect(tacticalApi.fetchTacticalStatus).toHaveBeenCalledWith("p1");
    expect(screen.getByText("기타 종목")).toBeDefined();
    expect(screen.getByText(/QQQ·SPY·DIA·QLD·SSO·현금 외 종목이 있어요/)).toBeDefined();
    // 지표는 접힘 안 — 펼치기 전엔 보이지 않는다
    expect(screen.queryByText("추세 상승")).toBeNull();
    await openDetails();
    expect(screen.getAllByText("추세 상승")).toHaveLength(2);
    // 비중표에 DIA가 없으면 DIA 참고 지표·비중 비교 행 모두 숨긴다
    expect(screen.queryByText("참고 · 국면 판단 미반영")).toBeNull();
    expect(screen.queryByText("DIA (다우존스)")).toBeNull();
  });

  it("비중표에 DIA가 있으면 DIA 참고 지표를 보여준다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({
        regime_weights: {
          ...DEFAULT_TABLE,
          NEUTRAL: { ...DEFAULT_TABLE.NEUTRAL, SPY: 20, DIA: 20 },
        },
      }),
    );
    renderTab();
    await openDetails();
    expect(screen.getByText("참고 · 국면 판단 미반영")).toBeDefined();
    expect(screen.getByText("추세 혼조")).toBeDefined();
  });

  it("매크로 확정 등급이 진단 탭 신호와 다를 수 있는 이유를 툴팁 없이 화면에 적는다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus());
    renderTab();
    await openDetails();

    expect(await screen.findByText(/진단 탭보다 늦게 바뀔 수 있어요/)).toBeDefined();
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
    expect(await screen.findByText("DIA (다우존스)")).toBeDefined();
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
      }),
    );
  });

  it("웅덩이 단계 배지와 이평선 이격을 보여준다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus());
    renderTab();
    expect(await screen.findByText("사용 안 함")).toBeDefined();
    await openDetails();

    expect(await screen.findByText("60일선 웅덩이")).toBeDefined();
    // QQQ 종가 716.19 / 20일선 730 → -1.9%
    expect(screen.getByText("-1.9%")).toBeDefined();
    // 웅덩이 배지는 투입 기준인 QQQ에만
    expect(screen.getAllByText("60일선 웅덩이")).toHaveLength(1);
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
    fireEvent.click(buttons[buttons.length - 1]);
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

  it("전략이 꺼져 있으면 비중표 편집을 보여주지 않는다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(
      makeStatus({ enabled: false, confirmed_regime: null }),
    );
    renderTab();
    await screen.findByText(/전술 배분 켜기/);
    expect(screen.queryByText("비중표 편집")).toBeNull();
  });

  it("포트폴리오를 바꾸면 그 포트폴리오로 다시 조회한다", async () => {
    vi.mocked(tacticalApi.fetchTacticalStatus).mockResolvedValue(makeStatus());
    renderTab();
    await screen.findByText("공격");

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "p2" } });
    await waitFor(() => expect(tacticalApi.fetchTacticalStatus).toHaveBeenCalledWith("p2"));
  });
});
