import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { FxExtraNeed } from "@/api/invest";
import type { ExchangeRateAlert } from "@/api/alerts";

vi.mock("@/api/invest", () => ({
  fetchFxExtraNeeds: vi.fn(),
  createFxExtraNeed: vi.fn(),
  updateFxExtraNeed: vi.fn(),
  deleteFxExtraNeed: vi.fn(),
  syncFxExtraNeedAlerts: vi.fn(),
}));
vi.mock("@/api/alerts", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/alerts")>()),
  fetchExchangeRateAlerts: vi.fn(),
}));
vi.mock("@/utils/queryInvalidation", () => ({ invalidateFxExtraNeedData: vi.fn() }));
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

import {
  createFxExtraNeed,
  deleteFxExtraNeed,
  fetchFxExtraNeeds,
  syncFxExtraNeedAlerts,
  updateFxExtraNeed,
} from "@/api/invest";
import { fetchExchangeRateAlerts } from "@/api/alerts";
import FxExtraNeedsSection from "@/components/invest/FxExtraNeedsSection";

const need = (over: Partial<FxExtraNeed> = {}): FxExtraNeed => ({
  id: "n1",
  name: "도쿄 여행",
  amount_usd: 1000,
  exchanged_usd: 250,
  remaining_usd: 750,
  due_date: "2026-12-20",
  days_left: 39,
  status: "OK",
  tranches: [
    { label: "지금", target_rate: null, usd: 255, krw_estimate: 357_000 },
    { label: "1,380원 이하", target_rate: 1380, usd: 247.5, krw_estimate: 341_550 },
    { label: "1,360원 이하", target_rate: 1360, usd: 247.5, krw_estimate: 336_600 },
  ],
  ...over,
});

const mockNeeds = (needs: FxExtraNeed[]) =>
  vi.mocked(fetchFxExtraNeeds).mockResolvedValue({ rate: 1400, rate_is_live: true, needs });

const planAlert = (rate: number, over: Partial<ExchangeRateAlert> = {}): ExchangeRateAlert => ({
  id: `a-${rate}`,
  target_rate: rate,
  direction: "BELOW",
  is_active: true,
  max_trigger_count: 1,
  trigger_count: 0,
  triggered_at: null,
  created_at: "2026-11-11T00:00:00Z",
  source: "FX_PLAN",
  planned_usd: 247.5,
  fx_need_id: "n1",
  ...over,
});

describe("FxExtraNeedsSection (plans/123)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([]);
    vi.mocked(syncFxExtraNeedAlerts).mockResolvedValue({
      created: 2,
      updated: 0,
      removed: 0,
      skipped_manual: 0,
    });
  });

  it("항목이 없으면 등록 안내를 보여준다", async () => {
    mockNeeds([]);
    renderWithProviders(<FxExtraNeedsSection />);
    expect(await screen.findByText("추가 환전 등록")).toBeInTheDocument();
  });

  it("D-N·진행·구간을 보여주고 목표 구간 알림을 항목 범위로 등록한다", async () => {
    mockNeeds([need()]);
    renderWithProviders(<FxExtraNeedsSection />);

    expect(await screen.findByText("도쿄 여행")).toBeInTheDocument();
    expect(screen.getByText("12월 20일 · D-39")).toBeInTheDocument();
    expect(screen.getByText("환전 $250 / $1,000")).toBeInTheDocument();
    expect(screen.getByText("1,380원 이하")).toBeInTheDocument();

    const button = await screen.findByRole("button", { name: "목표 환율 알림 등록" });
    fireEvent.click(button);
    await waitFor(() =>
      expect(syncFxExtraNeedAlerts).toHaveBeenCalledWith("n1", [
        { target_rate: 1380, usd: 247.5 },
        { target_rate: 1360, usd: 247.5 },
      ]),
    );
  });

  it("이 항목 알림이 모두 등록돼 있으면 버튼이 잠긴다 — 다른 항목·포트폴리오 알림은 세지 않는다", async () => {
    mockNeeds([need()]);
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([
      planAlert(1380),
      planAlert(1360),
      planAlert(1340, { id: "other", fx_need_id: "n2" }),
      planAlert(1320, { id: "p", fx_need_id: null, portfolio_id: "p1" }),
    ]);
    renderWithProviders(<FxExtraNeedsSection />);
    expect(await screen.findByRole("button", { name: "목표 환율 알림 등록됨" })).toBeDisabled();
  });

  it("지난 항목은 구간 대신 삭제 안내, 남은 계획 알림은 해제만 할 수 있다", async () => {
    mockNeeds([need({ status: "PAST_DUE", days_left: -2, tranches: [] })]);
    vi.mocked(fetchExchangeRateAlerts).mockResolvedValue([planAlert(1380)]);
    renderWithProviders(<FxExtraNeedsSection />);

    expect(await screen.findByText(/필요일이 지났습니다/)).toBeInTheDocument();
    expect(screen.getByText("12월 20일 · 지남")).toBeInTheDocument();
    fireEvent.click(
      await screen.findByRole("button", { name: "이 계획으로 등록한 알림 1건 해제" }),
    );
    await waitFor(() => expect(syncFxExtraNeedAlerts).toHaveBeenCalledWith("n1", []));
  });

  it("다 바꾼 항목은 완료로 보여주고 알림 버튼이 없다", async () => {
    mockNeeds([need({ status: "DONE", exchanged_usd: 1000, remaining_usd: 0, tranches: [] })]);
    renderWithProviders(<FxExtraNeedsSection />);
    expect(await screen.findByText("필요한 달러를 모두 바꿨습니다.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /알림/ })).not.toBeInTheDocument();
  });

  it("환전 완료로 표시하면 이미 환전한 금액을 전액으로 바꾼다", async () => {
    mockNeeds([need()]);
    vi.mocked(updateFxExtraNeed).mockResolvedValue(need());
    renderWithProviders(<FxExtraNeedsSection />);

    fireEvent.click(await screen.findByRole("button", { name: "도쿄 여행 더 보기" }));
    fireEvent.click(screen.getByText("환전 완료로 표시"));
    await waitFor(() =>
      expect(updateFxExtraNeed).toHaveBeenCalledWith("n1", { exchanged_usd: 1000 }),
    );
  });

  it("삭제는 확인 후 진행한다", async () => {
    mockNeeds([need()]);
    vi.mocked(deleteFxExtraNeed).mockResolvedValue(undefined);
    renderWithProviders(<FxExtraNeedsSection />);

    fireEvent.click(await screen.findByRole("button", { name: "도쿄 여행 더 보기" }));
    fireEvent.click(screen.getByText("삭제"));
    expect(screen.getByText(/목표 환율 알림도 함께 삭제됩니다/)).toBeInTheDocument();
    expect(deleteFxExtraNeed).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "삭제" }));
    await waitFor(() => expect(deleteFxExtraNeed).toHaveBeenCalledWith("n1"));
  });

  it("새 항목을 등록한다", async () => {
    mockNeeds([]);
    vi.mocked(createFxExtraNeed).mockResolvedValue(need());
    renderWithProviders(<FxExtraNeedsSection />);

    fireEvent.click(await screen.findByText("추가 환전 등록"));
    fireEvent.change(await screen.findByLabelText("이름"), { target: { value: " 도쿄 여행 " } });
    fireEvent.change(screen.getByLabelText("필요한 금액 (USD)"), { target: { value: "1,000" } });
    fireEvent.change(screen.getByLabelText("필요일"), { target: { value: "2099-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() =>
      expect(createFxExtraNeed).toHaveBeenCalledWith({
        name: "도쿄 여행",
        amount_usd: 1000,
        exchanged_usd: 0,
        due_date: "2099-01-01",
      }),
    );
  });

  it("이미 환전한 금액이 필요한 금액보다 크면 저장하지 않는다", async () => {
    mockNeeds([]);
    renderWithProviders(<FxExtraNeedsSection />);

    fireEvent.click(await screen.findByText("추가 환전 등록"));
    fireEvent.change(await screen.findByLabelText("이름"), { target: { value: "여행" } });
    fireEvent.change(screen.getByLabelText("필요한 금액 (USD)"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("필요일"), { target: { value: "2099-01-01" } });
    fireEvent.change(screen.getByLabelText("이미 환전한 금액 (USD, 선택)"), {
      target: { value: "200" },
    });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("필요한 금액보다 클 수 없습니다");
    expect(createFxExtraNeed).not.toHaveBeenCalled();
  });
});
