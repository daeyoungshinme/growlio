import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { TaxAction, TaxActionPlan } from "@/api/tax";
import { fmtKrw } from "@/utils/format";

const fetchTaxActionPlan = vi.fn();
const updateIncomeBracket = vi.fn();

vi.mock("@/api/tax", () => ({
  fetchTaxActionPlan: (...args: unknown[]) => fetchTaxActionPlan(...args),
}));

vi.mock("@/api/settings", () => ({
  updateIncomeBracket: (...args: unknown[]) => updateIncomeBracket(...args),
}));

import TaxActionPlanCard from "@/components/tax/TaxActionPlanCard";

function makeAction(overrides: Partial<TaxAction> = {}): TaxAction {
  return {
    id: "a",
    category: "ISA_CONTRIBUTION",
    title: "ISA에 올해 5,000,000원 더 납입 가능",
    detail: "상세 설명",
    amount_krw: 5_000_000,
    benefit_krw: null,
    deadline: null,
    priority: "LOW",
    uses_income_bracket: false,
    cta: { label: "입금 내역 기록", link: "/assets?tab=계좌관리" },
    ...overrides,
  };
}

function makePlan(actions: TaxAction[], income_bracket: TaxActionPlan["income_bracket"] = null) {
  return { year: 2026, income_bracket, actions, note: "참고용 추정치" } satisfies TaxActionPlan;
}

function renderCard() {
  return renderWithProviders(
    <MemoryRouter>
      <TaxActionPlanCard />
    </MemoryRouter>,
  );
}

describe("TaxActionPlanCard", () => {
  beforeEach(() => {
    fetchTaxActionPlan.mockReset();
    updateIncomeBracket.mockReset();
  });

  it("액션이 없으면 빈 상태 문구를 보여준다", async () => {
    fetchTaxActionPlan.mockResolvedValue(makePlan([]));
    renderCard();
    expect(await screen.findByText(/지금 챙길 절세 액션이 없어요/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "총급여 구간" })).toBeNull();
  });

  it("액션별 우선순위·절세액·CTA 링크를 렌더한다", async () => {
    fetchTaxActionPlan.mockResolvedValue(
      makePlan([
        makeAction({
          id: "loss",
          category: "TAX_LOSS_HARVEST",
          title: "AAPL 손실 1,000,000원 실현 검토",
          benefit_krw: 220_000,
          priority: "HIGH",
          cta: { label: "손실수확 보기", link: "/assets?tab=투자현황&portfolioTab=세금" },
        }),
      ]),
    );
    renderCard();
    expect(await screen.findByText("AAPL 손실 1,000,000원 실현 검토")).toBeInTheDocument();
    expect(screen.getByText("우선")).toBeInTheDocument();
    expect(screen.getByText(`절세 약 ${fmtKrw(220_000)}`)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /손실수확 보기/ })).toHaveAttribute(
      "href",
      "/assets?tab=투자현황&portfolioTab=세금",
    );
  });

  it("4개 이상이면 3개만 보여주고 더 보기로 펼친다", async () => {
    fetchTaxActionPlan.mockResolvedValue(
      makePlan([1, 2, 3, 4, 5].map((n) => makeAction({ id: `a${n}`, title: `액션 ${n}` }))),
    );
    renderCard();
    expect(await screen.findByText("액션 3")).toBeInTheDocument();
    expect(screen.queryByText("액션 4")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "2개 더 보기" }));
    expect(screen.getByText("액션 5")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "접기" })).toBeInTheDocument();
  });

  it("연금 관련 액션이 있으면 소득 구간을 인라인으로 입력받아 저장한다", async () => {
    fetchTaxActionPlan.mockResolvedValue(
      makePlan([makeAction({ id: "pension", uses_income_bracket: true })], "OVER_55M"),
    );
    updateIncomeBracket.mockResolvedValue({});
    renderCard();

    const over = await screen.findByRole("button", { name: "5,500만원 초과" });
    expect(over).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "5,500만원 이하" }));
    await waitFor(() => expect(updateIncomeBracket).toHaveBeenCalledWith("UNDER_55M"));
  });
});
