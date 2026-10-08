import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { ActionItem } from "@/api/dashboard";

const fetchActionItems = vi.fn();
vi.mock("@/api/dashboard", () => ({
  fetchActionItems: (...args: unknown[]) => fetchActionItems(...args),
}));

import ActionItemsCard from "@/components/dashboard/ActionItemsCard";

const rebalance: ActionItem = {
  id: "rebalance:p1",
  kind: "REBALANCE",
  priority: "HIGH",
  title: "성장형 리밸런싱 필요",
  detail: "최대 7.4%p 이탈 · 2종목이 기준 5%p 초과",
  cta_label: "점검하기",
  link: "/rebalancing?rtab=포트폴리오&portfolioId=p1",
  deadline: null,
};
const challenge: ActionItem = {
  id: "challenge:this-month",
  kind: "CHALLENGE",
  priority: "MEDIUM",
  title: "이번 달 적립 챌린지 입금 전",
  detail: "아직 입금하지 않은 챌린지 1개",
  cta_label: "챌린지 보기",
  link: "/invest-plan?tab=챌린지",
  deadline: "2099-12-31",
};

function renderCard() {
  return renderWithProviders(
    <MemoryRouter>
      <ActionItemsCard />
    </MemoryRouter>,
  );
}

describe("ActionItemsCard — 홈 지금 할 일 (docs/plans/50 M5)", () => {
  beforeEach(() => {
    localStorage.clear();
    fetchActionItems.mockReset();
  });

  it("항목을 우선순위 배지·CTA·마감과 함께 링크 행으로 보여준다", async () => {
    fetchActionItems.mockResolvedValue([rebalance, challenge]);
    renderCard();

    const row = (await screen.findByText("성장형 리밸런싱 필요")).closest("a");
    expect(row).toHaveAttribute("href", "/rebalancing?rtab=포트폴리오&portfolioId=p1");
    expect(screen.getByText("이번 달 적립 챌린지 입금 전").closest("a")).toHaveAttribute(
      "href",
      "/invest-plan?tab=챌린지",
    );
    expect(screen.getByText("권장")).toBeInTheDocument();
    expect(screen.getByText(/12\/31까지/)).toBeInTheDocument();
    // 헤더 배지: HIGH 개수
    expect(screen.getByText("우선 1")).toBeInTheDocument();
  });

  it("HIGH가 없으면 헤더 배지는 전체 건수를 보여준다", async () => {
    fetchActionItems.mockResolvedValue([challenge]);
    renderCard();
    expect(await screen.findByText("1건")).toBeInTheDocument();
  });

  it("접으면 첫 항목 제목을 힌트로 남기고 상태를 저장한다", async () => {
    fetchActionItems.mockResolvedValue([rebalance, challenge]);
    renderCard();
    await screen.findByText("점검하기");

    fireEvent.click(screen.getByRole("button", { name: /지금 할 일/ }));
    expect(screen.queryByText("점검하기")).not.toBeInTheDocument();
    expect(screen.getByText("성장형 리밸런싱 필요")).toBeInTheDocument();
    expect(localStorage.getItem("growlio:dashboard:actionItemsOpen")).toBe("false");
  });

  it("할 일이 없으면 한 줄 안내만 보여준다", async () => {
    fetchActionItems.mockResolvedValue([]);
    renderCard();
    expect(await screen.findByText(/지금 할 일이 없어요/)).toBeInTheDocument();
  });

  it("조회 실패 시 아무것도 렌더하지 않는다 (홈 전체를 막지 않음)", async () => {
    fetchActionItems.mockRejectedValue(new Error("boom"));
    const { container } = renderCard();
    await vi.waitFor(() => expect(fetchActionItems).toHaveBeenCalled());
    await vi.waitFor(() => expect(container.querySelector(".card")).toBeNull());
    expect(screen.queryByText(/지금 할 일/)).not.toBeInTheDocument();
  });
});
