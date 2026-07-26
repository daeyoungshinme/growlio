import { useState } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import GoalSettingWizard from "@/components/invest/GoalSettingWizard";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { GoalForm } from "@/hooks/useGoalSettings";

const fetchPortfolioOverviewLite = vi.fn();
const fetchGoalFeasibility = vi.fn();
const fetchOverallGoalRecommendation = vi.fn();
const createPortfolio = vi.fn();

vi.mock("@/api/portfolios", () => ({
  fetchPortfolioOverviewLite: (...args: unknown[]) => fetchPortfolioOverviewLite(...args),
  createPortfolio: (...args: unknown[]) => createPortfolio(...args),
}));

vi.mock("@/api/invest", () => ({
  fetchGoalFeasibility: (...args: unknown[]) => fetchGoalFeasibility(...args),
}));

vi.mock("@/api/rebalancing", () => ({
  fetchOverallGoalRecommendation: (...args: unknown[]) => fetchOverallGoalRecommendation(...args),
}));

const EMPTY_FORM: GoalForm = {
  monthly_deposit_amount: "",
  goal_annual_return_pct: "",
  goal_amount: "",
  goal_start_date: "",
  goal_initial_amount: "",
  annual_deposit_goal: "",
  retirement_target_year: "",
  birth_year: "",
  annual_dividend_goal: "",
  goal_risk_tolerance: "CONSERVATIVE",
};

function Harness({
  initialStep = 1,
  initialForm = EMPTY_FORM,
  onSaveImpl,
  onClose = vi.fn(),
}: {
  initialStep?: number;
  initialForm?: GoalForm;
  /** 저장 트리거 감지 로직(5단계→6단계 진입 시 자동 저장, saving true→false 전환 감지)을
   * 테스트하려면 실제 saving 상태를 흉내내야 하므로, 호출측이 setSaving을 받아 직접 제어한다. */
  onSaveImpl?: (setSaving: (v: boolean) => void) => void;
  onClose?: () => void;
}) {
  const [form, setForm] = useState<GoalForm>(initialForm);
  const [step, setStep] = useState(initialStep);
  const [saving, setSaving] = useState(false);
  return (
    <GoalSettingWizard
      form={form}
      setForm={setForm}
      step={step}
      setStep={setStep}
      saving={saving}
      onSave={() => onSaveImpl?.(setSaving)}
      onClose={onClose}
    />
  );
}

function renderWizard(props?: Parameters<typeof Harness>[0]) {
  return renderWithProviders(
    <MemoryRouter>
      <Harness {...props} />
    </MemoryRouter>,
  );
}

describe("GoalSettingWizard", () => {
  beforeEach(() => {
    fetchPortfolioOverviewLite.mockReset();
    fetchGoalFeasibility.mockReset();
    fetchOverallGoalRecommendation.mockReset();
    createPortfolio.mockReset();
    fetchPortfolioOverviewLite.mockResolvedValue({
      total_assets_krw: 100_000_000,
      asset_type_allocation: [],
    });
    createPortfolio.mockResolvedValue({ id: "new-portfolio" });
  });

  it("1단계: 현재 자산 힌트를 표시한다", async () => {
    renderWizard();
    expect(screen.getByText("현재 자산 확인")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/현재 투자자산\(부동산 제외\) 약/)).toBeInTheDocument();
    });
  });

  it("1단계: 부동산 자산은 현재 자산 힌트/초기값에서 제외된다", async () => {
    fetchPortfolioOverviewLite.mockResolvedValue({
      total_assets_krw: 100_000_000,
      asset_type_allocation: [
        { type: "STOCK_KIS", amount_krw: 60_000_000, label: "국내주식", pct: 60 },
        { type: "REAL_ESTATE", amount_krw: 40_000_000, label: "부동산", pct: 40 },
      ],
    });
    renderWizard();
    await waitFor(() => {
      // 총자산 100M 중 부동산 40M을 뺀 60M만 초기 자산으로 반영되어야 함
      expect(screen.getByText(/현재 투자자산\(부동산 제외\) 약 6,000만원/)).toBeInTheDocument();
    });
  });

  it("2단계: 목표 금액/시점을 입력하지 않으면 다음 버튼이 비활성화된다", () => {
    renderWizard({ initialStep: 2 });
    expect(screen.getByRole("button", { name: "다음" })).toBeDisabled();
  });

  it("2단계: 목표 금액/시점을 입력하면 다음으로 진행할 수 있다", () => {
    renderWizard({ initialStep: 2 });
    fireEvent.change(screen.getByLabelText(/목표 금액 \(원\)/), { target: { value: "500000000" } });
    fireEvent.change(screen.getByLabelText(/목표 시점 \(연도\)/), { target: { value: "2045" } });
    expect(screen.getByRole("button", { name: "다음" })).not.toBeDisabled();
    expect(screen.getByText("500,000,000원 (5.00억원)")).toBeInTheDocument();
  });

  it("3단계: 월 적립액을 입력하면 연간 입금 목표가 자동 계산된다", () => {
    renderWizard({ initialStep: 3 });
    fireEvent.change(screen.getByLabelText("월 적립액 (원)"), { target: { value: "500000" } });
    expect(screen.getByLabelText("연간 입금 목표 (원)")).toHaveValue(6000000);
  });

  it("3단계: 가정 수익률별 필요 적립액 가이드를 표시하고 채우기 버튼으로 적립액을 채울 수 있다", async () => {
    fetchGoalFeasibility.mockResolvedValue({
      required_return_pct: 9,
      pv: 0,
      n_months: 120,
      note: null,
      deposit_guide: [
        {
          annual_return_pct: 4,
          required_monthly_deposit: 680000,
          required_annual_deposit: 8160000,
        },
        {
          annual_return_pct: 7,
          required_monthly_deposit: 580000,
          required_annual_deposit: 6960000,
        },
        {
          annual_return_pct: 10,
          required_monthly_deposit: 490000,
          required_annual_deposit: 5880000,
        },
      ],
    });
    renderWizard({
      initialStep: 3,
      initialForm: { ...EMPTY_FORM, goal_amount: "500000000", retirement_target_year: "2045" },
    });
    await waitFor(() => {
      expect(screen.getByText("월 58만원")).toBeInTheDocument();
    });
    fireEvent.click(screen.getAllByRole("button", { name: "이 값으로 채우기" })[1]);
    expect(screen.getByLabelText("월 적립액 (원)")).toHaveValue(580000);
    expect(screen.getByLabelText("연간 입금 목표 (원)")).toHaveValue(6960000);
  });

  it("4단계: 필요 수익률을 조회해 표시하고 목표 연수익률을 prefill한다", async () => {
    fetchGoalFeasibility.mockResolvedValue({
      required_return_pct: 7.5,
      pv: 100_000_000,
      n_months: 120,
      note: null,
      deposit_guide: [],
    });
    renderWizard({
      initialStep: 4,
      initialForm: {
        ...EMPTY_FORM,
        goal_amount: "500000000",
        retirement_target_year: "2045",
        monthly_deposit_amount: "500000",
      },
    });
    await waitFor(() => {
      expect(screen.getByText("+7.50%")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByLabelText("목표 연수익률 (%)")).toHaveValue(7.5);
    });
  });

  it("4단계: 달성 불가능한 목표는 안내 문구를 표시한다", async () => {
    fetchGoalFeasibility.mockResolvedValue({
      required_return_pct: null,
      pv: 100_000_000,
      n_months: 12,
      note: "현재 조건(적립액·기간)으로는 달성이 매우 어려운 목표입니다",
      deposit_guide: [],
    });
    renderWizard({
      initialStep: 4,
      initialForm: {
        ...EMPTY_FORM,
        goal_amount: "1000000000000",
        retirement_target_year: "2027",
      },
    });
    await waitFor(() => {
      expect(
        screen.getByText("현재 조건(적립액·기간)으로는 달성이 매우 어려운 목표입니다"),
      ).toBeInTheDocument();
    });
  });

  it("5단계: 출생연도·투자성향·배당목표를 입력할 수 있다", () => {
    renderWizard({ initialStep: 5 });
    fireEvent.change(screen.getByLabelText("출생연도"), { target: { value: "1990" } });
    fireEvent.change(screen.getByLabelText("투자성향"), { target: { value: "AGGRESSIVE" } });
    fireEvent.change(screen.getByLabelText("연간 배당목표 (원)"), {
      target: { value: "3000000" },
    });
    expect(screen.getByLabelText("출생연도")).toHaveValue(1990);
    expect(screen.getByLabelText("투자성향")).toHaveValue("AGGRESSIVE");
    expect(screen.getByLabelText("연간 배당목표 (원)")).toHaveValue(3000000);
  });

  it("6단계 진입 시 onSave가 자동으로 1회 호출된다", () => {
    fetchOverallGoalRecommendation.mockResolvedValue(undefined);
    const onSaveImpl = vi.fn();
    renderWizard({ initialStep: 6, onSaveImpl });
    expect(onSaveImpl).toHaveBeenCalledTimes(1);
  });

  it("6단계: 저장이 완료되면 추천 포트폴리오를 조회해 보여주고, 포트폴리오 만들기 버튼으로 생성한다", async () => {
    fetchOverallGoalRecommendation.mockResolvedValue({
      generated_at: "2026-07-26T00:00:00Z",
      is_configured: true,
      required_return_pct: 7,
      required_dividend_yield_pct: null,
      recommended_items: [
        {
          ticker: "069500",
          name: "KODEX 200",
          market: "KOSPI",
          weight: 100,
          dividend_yield_pct: null,
        },
      ],
      expected_return_pct: 8,
      expected_dividend_yield_pct: null,
      expected_volatility_pct: 12,
      note: null,
      cagr_lookback_years: 10,
      risk_tolerance: "CONSERVATIVE",
      max_weight_pct: 40,
      market_signal_level: null,
      suggested_candidates: [],
    });
    let capturedSetSaving: ((v: boolean) => void) | null = null;
    const onSaveImpl = vi.fn((setSaving: (v: boolean) => void) => {
      capturedSetSaving = setSaving;
      setSaving(true);
    });
    renderWizard({ initialStep: 6, onSaveImpl });
    expect(screen.getByText(/추천 포트폴리오를 계산하고 있어요/)).toBeInTheDocument();

    act(() => {
      capturedSetSaving?.(false);
    });

    await waitFor(() => {
      expect(screen.getByText("KODEX 200")).toBeInTheDocument();
    });
    expect(screen.getByText("100.0%")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "이 추천으로 포트폴리오 만들기" }));
    await waitFor(() => {
      expect(createPortfolio).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "추천 포트폴리오",
          items: [{ ticker: "069500", name: "KODEX 200", market: "KOSPI", weight: 100 }],
        }),
      );
    });
  });

  it("6단계: 완료 버튼을 누르면 onClose가 호출된다", () => {
    fetchOverallGoalRecommendation.mockResolvedValue(undefined);
    const onClose = vi.fn();
    renderWizard({ initialStep: 6, onSaveImpl: vi.fn(), onClose });
    fireEvent.click(screen.getByRole("button", { name: "완료" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("이전 버튼으로 단계를 되돌릴 수 있다", () => {
    renderWizard({ initialStep: 2 });
    fireEvent.click(screen.getByRole("button", { name: "이전" }));
    expect(screen.getByText("현재 자산 확인")).toBeInTheDocument();
  });

  it("닫기 버튼을 누르면 onClose가 호출된다", () => {
    const onClose = vi.fn();
    renderWizard({ onClose });
    fireEvent.click(screen.getByLabelText("닫기"));
    expect(onClose).toHaveBeenCalled();
  });
});
