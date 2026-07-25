import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import RecommendationApplySection from "@/components/rebalancing/RecommendationApplySection";
import type { Portfolio } from "@/api/portfolios";

function makePortfolio(overrides: Partial<Portfolio> = {}): Portfolio {
  return {
    id: "port-1",
    name: "메인 포트폴리오",
    items: [],
    base_type: "STOCK_ONLY",
    sort_order: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("RecommendationApplySection", () => {
  it("대상 포트폴리오가 없으면 안내 문구를 표시한다", () => {
    renderWithProviders(
      <RecommendationApplySection
        targetPortfolios={[]}
        selectedTargetId=""
        onSelectTarget={vi.fn()}
        onApplyClick={vi.fn()}
        applyPending={false}
        noTargetMessage="포트폴리오를 지정해주세요"
      />,
    );
    expect(screen.getByText("포트폴리오를 지정해주세요")).toBeInTheDocument();
  });

  it("대상이 1개면 select 없이 이름으로 바로 적용 버튼을 표시한다", () => {
    renderWithProviders(
      <RecommendationApplySection
        targetPortfolios={[makePortfolio()]}
        selectedTargetId=""
        onSelectTarget={vi.fn()}
        onApplyClick={vi.fn()}
        applyPending={false}
        noTargetMessage="안내"
      />,
    );
    expect(screen.getByRole("button", { name: "메인 포트폴리오에 적용" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("대상이 2개 이상이면 select를 표시하고 미선택 시 적용 버튼이 비활성화된다", () => {
    renderWithProviders(
      <RecommendationApplySection
        targetPortfolios={[
          makePortfolio({ id: "a", name: "포트폴리오 A" }),
          makePortfolio({ id: "b", name: "포트폴리오 B" }),
        ]}
        selectedTargetId=""
        onSelectTarget={vi.fn()}
        onApplyClick={vi.fn()}
        applyPending={false}
        noTargetMessage="안내"
      />,
    );
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "기준 포트폴리오에 적용" })).toBeDisabled();
  });

  it("적용 버튼 클릭 시 onApplyClick을 호출한다", () => {
    const onApplyClick = vi.fn();
    renderWithProviders(
      <RecommendationApplySection
        targetPortfolios={[makePortfolio()]}
        selectedTargetId=""
        onSelectTarget={vi.fn()}
        onApplyClick={onApplyClick}
        applyPending={false}
        noTargetMessage="안내"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "메인 포트폴리오에 적용" }));
    expect(onApplyClick).toHaveBeenCalledOnce();
  });

  it("onCreatePortfolio가 없으면 새 포트폴리오 만들기 버튼을 렌더하지 않는다", () => {
    renderWithProviders(
      <RecommendationApplySection
        targetPortfolios={[makePortfolio()]}
        selectedTargetId=""
        onSelectTarget={vi.fn()}
        onApplyClick={vi.fn()}
        applyPending={false}
        noTargetMessage="안내"
      />,
    );
    expect(screen.queryByText(/새 포트폴리오 만들기/)).toBeNull();
  });

  it("onCreatePortfolio가 있으면 클릭 시 호출한다", () => {
    const onCreatePortfolio = vi.fn();
    renderWithProviders(
      <RecommendationApplySection
        targetPortfolios={[makePortfolio()]}
        selectedTargetId=""
        onSelectTarget={vi.fn()}
        onApplyClick={vi.fn()}
        applyPending={false}
        noTargetMessage="안내"
        onCreatePortfolio={onCreatePortfolio}
      />,
    );
    fireEvent.click(screen.getByText(/새 포트폴리오 만들기/));
    expect(onCreatePortfolio).toHaveBeenCalledOnce();
  });

  it("extraCopyBeforeButtons를 전달하면 함께 렌더한다", () => {
    renderWithProviders(
      <RecommendationApplySection
        targetPortfolios={[makePortfolio()]}
        selectedTargetId=""
        onSelectTarget={vi.fn()}
        onApplyClick={vi.fn()}
        applyPending={false}
        noTargetMessage="안내"
        extraCopyBeforeButtons={<p>현금성 자산 자동 연결 안내</p>}
      />,
    );
    expect(screen.getByText("현금성 자산 자동 연결 안내")).toBeInTheDocument();
  });
});
