import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { DipBuyPlan } from "@/api/dipBuy";

vi.mock("@/api/dipBuy", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/dipBuy")>()),
  fetchDipBuyStatus: vi.fn(),
  completeDipBuy: vi.fn().mockResolvedValue(undefined),
  upsertDipBuyPlan: vi.fn().mockResolvedValue(undefined),
  deleteDipBuyPlan: vi.fn().mockResolvedValue(undefined),
}));
vi.mock("@/api/portfolios", () => ({
  fetchPortfolios: vi.fn().mockResolvedValue([
    { id: "port-1", name: "나스닥 적립", items: [], sort_order: 0 },
    { id: "port-2", name: "연금", items: [], sort_order: 1 },
  ]),
}));
vi.mock("@/api/alerts", () => ({ fetchRebalancingAlerts: vi.fn().mockResolvedValue([]) }));
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

import { completeDipBuy, fetchDipBuyStatus, upsertDipBuyPlan } from "@/api/dipBuy";
import DipBuyCard from "@/components/invest/DipBuyCard";

const plan = (over: Partial<DipBuyPlan> = {}): DipBuyPlan => ({
  id: "plan-1",
  portfolio_id: "port-1",
  portfolio_name: "나스닥 적립",
  is_active: true,
  index_ticker: "QQQ",
  reserve_krw: 10_000_000,
  cycle_base_krw: null,
  tiers: [
    {
      tier: 0,
      drawdown_pct: 10,
      ratio_pct: 20,
      amount_krw: 2_000_000,
      state: "DUE",
      done_amount_krw: null,
    },
    {
      tier: 1,
      drawdown_pct: 20,
      ratio_pct: 30,
      amount_krw: 3_000_000,
      state: "WAITING",
      done_amount_krw: null,
    },
    {
      tier: 2,
      drawdown_pct: 30,
      ratio_pct: 50,
      amount_krw: 5_000_000,
      state: "WAITING",
      done_amount_krw: null,
    },
  ],
  drawdown_pct: -12.3,
  has_dca_schedule: true,
  next_run_date: "2026-11-25",
  is_run_day: false,
  due_amount_krw: 2_000_000,
  due_tiers: [0],
  items: [
    {
      ticker: "QQQM",
      name: "Invesco QQQM",
      market: "NASDAQ",
      shares: 3,
      amount_krw: 900_000,
      price_krw: 300_000,
      amount_usd: 600,
    },
  ],
  leftover_krw: 100_000,
  ...over,
});

const renderCard = () =>
  renderWithProviders(
    <MemoryRouter>
      <DipBuyCard />
    </MemoryRouter>,
  );

describe("DipBuyCard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("구간 상태·이번 추매 금액·종목을 보여준다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue({ plans: [plan()], reset_drawdown_pct: 3 });
    renderCard();
    expect(await screen.findByText("이번 적립일에 추매 200만원")).toBeInTheDocument();
    expect(screen.getByText("-12.3%")).toBeInTheDocument();
    expect(screen.getByText("다음 적립일 11월 25일(수)")).toBeInTheDocument();
    expect(screen.getByText("이번 적립일")).toBeInTheDocument();
    expect(screen.getAllByText("대기")).toHaveLength(2);
    expect(screen.getByText("Invesco QQQM 3주")).toBeInTheDocument();
    expect(screen.getByText(/약 \$600/)).toBeInTheDocument();
    expect(screen.getByText("1주 단위로 나누고 남은 10만원")).toBeInTheDocument();
  });

  it("'추매했어요'는 산 금액을 확인받고 기록한다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue({ plans: [plan()], reset_drawdown_pct: 3 });
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "추매했어요" }));
    const input = screen.getByLabelText("산 금액 (원)");
    expect(input).toHaveValue("2000000");
    fireEvent.change(input, { target: { value: "1,800,000" } });
    fireEvent.click(screen.getByRole("button", { name: "기록하기" }));
    await waitFor(() => expect(completeDipBuy).toHaveBeenCalledWith("port-1", 1_800_000));
  });

  it("추매 구간이 없으면 회복 기준을 안내한다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue({
      plans: [plan({ due_amount_krw: 0, due_tiers: [], items: [], drawdown_pct: -4 })],
      reset_drawdown_pct: 3,
    });
    renderCard();
    expect(await screen.findByText(/지금은 추매할 구간이 없어요/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "추매했어요" })).not.toBeInTheDocument();
  });

  it("정기 적립식이 없으면 자동매수 설정 링크를 보여준다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue({
      plans: [plan({ has_dca_schedule: false, next_run_date: null, items: [] })],
      reset_drawdown_pct: 3,
    });
    renderCard();
    expect(await screen.findByRole("link", { name: "자동매수 설정" })).toHaveAttribute(
      "href",
      expect.stringContaining("openAlert=dca"),
    );
  });

  it("설정이 없으면 켜기 버튼으로 기본 구간을 저장한다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue({ plans: [], reset_drawdown_pct: 3 });
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "추매 안내 켜기" }));
    fireEvent.change(screen.getByLabelText("추매용 여윳돈 (원)"), {
      target: { value: "10000000" },
    });
    expect(screen.getByText("비율 합계 100% (100% 이하)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() =>
      expect(upsertDipBuyPlan).toHaveBeenCalledWith("port-1", {
        index_ticker: "QQQ",
        reserve_krw: 10_000_000,
        tiers: [
          { drawdown_pct: 10, ratio_pct: 20 },
          { drawdown_pct: 20, ratio_pct: 30 },
          { drawdown_pct: 30, ratio_pct: 50 },
        ],
        is_active: true,
      }),
    );
  });

  it("비율 합계가 100%를 넘으면 저장하지 않는다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue({ plans: [], reset_drawdown_pct: 3 });
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "추매 안내 켜기" }));
    fireEvent.change(screen.getByLabelText("추매용 여윳돈 (원)"), { target: { value: "1000000" } });
    fireEvent.change(screen.getByLabelText("3구간 여윳돈 비율(%)"), { target: { value: "60" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("100%를 넘을 수 없어요");
    expect(upsertDipBuyPlan).not.toHaveBeenCalled();
  });
});
