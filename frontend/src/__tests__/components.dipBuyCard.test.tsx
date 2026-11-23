import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { DipBuyRule, DipBuyStatus } from "@/api/dipBuy";

vi.mock("@/api/dipBuy", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/dipBuy")>()),
  fetchDipBuyStatus: vi.fn(),
  completeDipBuy: vi.fn().mockResolvedValue(undefined),
  upsertDipBuySettings: vi.fn().mockResolvedValue(undefined),
  createDipBuyRule: vi.fn().mockResolvedValue(undefined),
  updateDipBuyRule: vi.fn().mockResolvedValue(undefined),
  deleteDipBuyRule: vi.fn().mockResolvedValue(undefined),
}));
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

import {
  completeDipBuy,
  createDipBuyRule,
  fetchDipBuyStatus,
  upsertDipBuySettings,
} from "@/api/dipBuy";
import DipBuyCard from "@/components/invest/DipBuyCard";

const rule = (over: Partial<DipBuyRule> = {}): DipBuyRule => ({
  id: "rule-qqq",
  index_ticker: "QQQ",
  allocation_pct: 60,
  is_active: true,
  base_krw: 6_000_000,
  spent_krw: 0,
  remaining_krw: 6_000_000,
  tiers: [
    {
      tier: 0,
      drawdown_pct: 10,
      ratio_pct: 20,
      amount_krw: 1_200_000,
      state: "DUE",
      done_amount_krw: null,
    },
    {
      tier: 1,
      drawdown_pct: 20,
      ratio_pct: 30,
      amount_krw: 1_800_000,
      state: "WAITING",
      done_amount_krw: null,
    },
    {
      tier: 2,
      drawdown_pct: 30,
      ratio_pct: 50,
      amount_krw: 3_000_000,
      state: "WAITING",
      done_amount_krw: null,
    },
  ],
  drawdown_pct: -12.3,
  due_amount_krw: 1_200_000,
  due_tiers: [0],
  etfs: [
    {
      ticker: "QQQ",
      name: "Invesco QQQ",
      market: "NASDAQ",
      price_krw: 750_000,
      shares: 1,
      amount_krw: 750_000,
      amount_usd: 500,
    },
    {
      ticker: "133690",
      name: "TIGER 미국나스닥100",
      market: "KOSPI",
      price_krw: 130_000,
      shares: 9,
      amount_krw: 1_170_000,
      amount_usd: null,
    },
  ],
  ...over,
});

const status = (over: Partial<DipBuyStatus> = {}): DipBuyStatus => ({
  settings: { reserve_krw: 10_000_000, notify_mode: "ON_REACH", notify_day: null, is_active: true },
  rules: [rule()],
  next_notify_date: null,
  due_amount_krw: 1_200_000,
  dca_held_portfolios: [],
  has_candidates: true,
  reset_drawdown_pct: 3,
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

  it("여윳돈·알림 방식과 규칙별 구간·추매 금액·ETF 대안을 보여준다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue(status());
    renderCard();
    expect(await screen.findByText("추매 120만원")).toBeInTheDocument();
    expect(screen.getByText("남은 여윳돈 1,000만원")).toBeInTheDocument();
    expect(screen.getByText(/알림: 구간 도달 다음 날 아침/)).toBeInTheDocument();
    expect(screen.getByText("-12.3%")).toBeInTheDocument();
    expect(screen.getByText("지금 추매")).toBeInTheDocument();
    expect(screen.getAllByText("대기")).toHaveLength(2);
    expect(screen.getByText("계좌에 맞는 ETF 하나로 사세요")).toBeInTheDocument();
    expect(screen.getByText("Invesco QQQ 1주")).toBeInTheDocument();
    expect(screen.getByText("TIGER 미국나스닥100 9주")).toBeInTheDocument();
    expect(screen.getByText(/약 \$500/)).toBeInTheDocument();
  });

  it("매달 정한 날 방식이면 다음 알림일을 보여준다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue(
      status({
        settings: { reserve_krw: 1e7, notify_mode: "MONTHLY_DAY", notify_day: 25, is_active: true },
        next_notify_date: "2026-11-25",
      }),
    );
    renderCard();
    expect(await screen.findByText(/알림: 매달 25일 · 다음 11월 25일\(수\)/)).toBeInTheDocument();
  });

  it("'추매했어요'는 산 금액을 확인받고 그 규칙에 기록한다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue(status());
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "추매했어요" }));
    const input = screen.getByLabelText("산 금액 (원)");
    expect(input).toHaveValue("1200000");
    fireEvent.change(input, { target: { value: "1,170,000" } });
    fireEvent.click(screen.getByRole("button", { name: "기록하기" }));
    await waitFor(() => expect(completeDipBuy).toHaveBeenCalledWith("rule-qqq", 1_170_000));
  });

  it("추매 구간이 없으면 회복 기준을 안내한다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue(
      status({
        rules: [rule({ due_amount_krw: 0, due_tiers: [], etfs: [], drawdown_pct: -4 })],
        due_amount_krw: 0,
      }),
    );
    renderCard();
    expect(await screen.findByText(/지금은 추매할 구간이 없어요/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "추매했어요" })).not.toBeInTheDocument();
  });

  it("추천 후보에 그 지수 ETF가 없으면 후보 관리 링크를 보여준다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue(
      status({ rules: [rule({ etfs: [] })], has_candidates: false }),
    );
    renderCard();
    expect(await screen.findByRole("link", { name: "후보 ETF 관리" })).toHaveAttribute(
      "href",
      expect.stringContaining("gmode=%EC%B6%94%EC%B2%9C"),
    );
  });

  it("전술 방어 국면으로 적립 자동매수가 보류 중이면 함께 안내한다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue(
      status({ dca_held_portfolios: ["나스닥 적립"] }),
    );
    renderCard();
    expect(
      await screen.findByText(/나스닥 적립 적립 자동매수는 전술 방어 국면이라 보류 중/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "전술 국면 보기" })).toBeInTheDocument();
  });

  it("여윳돈이 없으면 여윳돈 정하기로 알림 방식과 함께 저장한다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue(
      status({ settings: null, rules: [], due_amount_krw: 0 }),
    );
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "여윳돈 정하기" }));
    fireEvent.change(screen.getByLabelText("추매용 여윳돈 (원)"), {
      target: { value: "10000000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "매달 정한 날" }));
    fireEvent.change(screen.getByLabelText("매달 알림일"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() =>
      expect(upsertDipBuySettings).toHaveBeenCalledWith({
        reserve_krw: 10_000_000,
        notify_mode: "MONTHLY_DAY",
        notify_day: 10,
        is_active: true,
      }),
    );
  });

  it("다른 지수 규칙 추가는 남은 지수·배분으로 기본 구간을 저장한다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue(status());
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "다른 지수 규칙 추가" }));
    expect(screen.getByText("S&P500 (SPY)")).toBeInTheDocument();
    expect(screen.getByLabelText("여윳돈 배분 (%)")).toHaveValue("40");
    expect(screen.getByText(/다른 규칙이 60%를 써서 40%까지/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() =>
      expect(createDipBuyRule).toHaveBeenCalledWith({
        index_ticker: "SPY",
        allocation_pct: 40,
        tiers: [
          { drawdown_pct: 10, ratio_pct: 20 },
          { drawdown_pct: 20, ratio_pct: 30 },
          { drawdown_pct: 30, ratio_pct: 50 },
        ],
        is_active: true,
      }),
    );
  });

  it("배분이 남은 몫을 넘거나 구간 비율 합계가 100%를 넘으면 저장하지 않는다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue(status());
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "다른 지수 규칙 추가" }));
    fireEvent.change(screen.getByLabelText("여윳돈 배분 (%)"), { target: { value: "50" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("40%까지 정할 수 있어요");
    fireEvent.change(screen.getByLabelText("여윳돈 배분 (%)"), { target: { value: "40" } });
    fireEvent.change(screen.getByLabelText("3구간 비율(%)"), { target: { value: "60" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("100%를 넘을 수 없어요");
    expect(createDipBuyRule).not.toHaveBeenCalled();
  });

  it("두 지수 규칙을 다 쓰면 추가 버튼을 숨긴다", async () => {
    vi.mocked(fetchDipBuyStatus).mockResolvedValue(
      status({
        rules: [rule(), rule({ id: "rule-spy", index_ticker: "SPY", allocation_pct: 40 })],
      }),
    );
    renderCard();
    expect(await screen.findByText("S&P500 (SPY)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다른 지수 규칙 추가" })).not.toBeInTheDocument();
  });
});
