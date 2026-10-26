import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { ActionItem } from "@/api/dashboard";
import type { MarketSignalResponse } from "@/api/marketSignals";

const fetchActionItems = vi.fn();
vi.mock("@/api/dashboard", () => ({
  fetchActionItems: (...args: unknown[]) => fetchActionItems(...args),
  REBALANCE_GROUP_ID: "rebalance:all",
}));
const fetchDriftSummary = vi.fn();
vi.mock("@/api/rebalancing", () => ({
  fetchDriftSummary: (...args: unknown[]) => fetchDriftSummary(...args),
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

function renderCard(marketSignal?: MarketSignalResponse | null) {
  return renderWithProviders(
    <MemoryRouter>
      <ActionItemsCard marketSignal={marketSignal} />
    </MemoryRouter>,
  );
}

const drift = (id: string, needs: boolean, maxDrift = needs ? 7 : 1) =>
  ({
    portfolio_id: id,
    portfolio_name: id,
    max_drift_pct: maxDrift,
    needs_rebalancing: needs,
    drifted_items_count: 2,
    threshold_pct: 5,
  }) as never;

const rebalanceGroup: ActionItem = {
  id: "rebalance:all",
  kind: "REBALANCE",
  priority: "HIGH",
  title: "리밸런싱 필요 · 포트폴리오 2개",
  detail: "배당형 최대 9.3%p 이탈 외 1개",
  cta_label: "자세히 보기",
  link: "/rebalancing",
  deadline: null,
};

describe("ActionItemsCard — 홈 지금 할 일 (docs/plans/50 M5)", () => {
  beforeEach(() => {
    localStorage.clear();
    fetchActionItems.mockReset();
    fetchDriftSummary.mockReset();
    fetchDriftSummary.mockResolvedValue([]);
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

  it("조회 실패 시 한 줄 안내와 다시 시도를 보여준다 (홈 전체를 막지 않음)", async () => {
    fetchActionItems.mockRejectedValue(new Error("boom"));
    renderCard();
    expect(await screen.findByText("지금 할 일을 불러오지 못했어요")).toBeInTheDocument();
    fetchActionItems.mockResolvedValue([]);
    fireEvent.click(screen.getByRole("button", { name: /다시 시도/ }));
    expect(await screen.findByText(/지금 할 일이 없어요/)).toBeInTheDocument();
  });

  it("4건 이상이면 3건만 보이고 나머지는 더 보기로 펼친다", async () => {
    const items = [1, 2, 3, 4].map((n) => ({ ...challenge, id: `c${n}`, title: `할 일 ${n}` }));
    fetchActionItems.mockResolvedValue(items);
    renderCard();
    expect(await screen.findByText("할 일 3")).toBeInTheDocument();
    expect(screen.queryByText("할 일 4")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /1개 더 보기/ }));
    expect(screen.getByText("할 일 4")).toBeInTheDocument();
  });

  describe("리밸런싱 행 시장 신호 배지 (docs/plans/73 — 하단 상태 줄 대체)", () => {
    it("단일 리밸런싱 행에만 시장 배지가 붙고 다른 종류 행에는 없다", async () => {
      fetchActionItems.mockResolvedValue([rebalance, challenge]);
      renderCard({ composite_level: "RED" } as MarketSignalResponse);
      const badge = await screen.findByText("시장 위험");
      expect(badge.closest("a")).toHaveAttribute(
        "href",
        "/rebalancing?rtab=포트폴리오&portfolioId=p1",
      );
      expect(screen.getAllByText(/^시장 /)).toHaveLength(1);
    });

    it("묶음 행에도 시장 배지가 붙는다", async () => {
      fetchActionItems.mockResolvedValue([rebalanceGroup]);
      renderCard({ composite_level: "GREEN" } as MarketSignalResponse);
      const badge = await screen.findByText("시장 안정");
      expect(badge.closest("button")).toHaveAttribute("aria-expanded", "false");
    });

    it("전술 행은 목표 조정 › 전술 링크 행이고 시장 배지가 없다 (docs/plans/75)", async () => {
      const tactical: ActionItem = {
        id: "tactical:p2",
        kind: "TACTICAL",
        priority: "HIGH",
        title: "미국 전술 전술: 공격 국면 비중 적용 전",
        detail: "제안 QQQ 50% · SPY 40% · 현금 10%",
        cta_label: "적용하기",
        link: "/rebalancing?rtab=목표 조정&gmode=전술&portfolioId=p2",
        deadline: null,
      };
      fetchActionItems.mockResolvedValue([tactical]);
      renderCard({ composite_level: "RED" } as MarketSignalResponse);
      const row = (await screen.findByText(tactical.title)).closest("a");
      expect(row).toHaveAttribute("href", tactical.link);
      expect(screen.queryByText(/^시장 /)).not.toBeInTheDocument();
    });

    it("시장 신호가 없으면 배지를 그리지 않는다", async () => {
      fetchActionItems.mockResolvedValue([rebalance]);
      renderCard();
      await screen.findByText("성장형 리밸런싱 필요");
      expect(screen.queryByText(/^시장 /)).not.toBeInTheDocument();
    });

    it("리밸런싱 행이 없으면 시장 배지도 없고 drift-summary를 조회하지 않는다", async () => {
      fetchActionItems.mockResolvedValue([challenge]);
      renderCard({ composite_level: "GREEN" } as MarketSignalResponse);
      await screen.findByText("이번 달 적립 챌린지 입금 전");
      expect(screen.queryByText("시장 안정")).not.toBeInTheDocument();
      expect(fetchDriftSummary).not.toHaveBeenCalled();
    });

    it("할 일이 없으면 한 줄 안내만 — 하단 리밸런싱 줄·시장 배지 없음", async () => {
      fetchActionItems.mockResolvedValue([]);
      renderCard({ composite_level: "RED" } as MarketSignalResponse);
      expect(await screen.findByText(/지금 할 일이 없어요/)).toBeInTheDocument();
      expect(screen.queryByText("시장 위험")).not.toBeInTheDocument();
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
      expect(fetchDriftSummary).not.toHaveBeenCalled();
    });
  });

  describe("리밸런싱 묶음 행 — 자세히 보기로 이탈 포트폴리오만 펼침 (docs/plans/73)", () => {
    it("처음엔 접혀 있고, 펼치면 이탈 포트폴리오만 이탈 큰 순으로 각 포트폴리오 탭 링크", async () => {
      fetchActionItems.mockResolvedValue([rebalanceGroup, challenge]);
      fetchDriftSummary.mockResolvedValue([
        drift("성장형", true, 6),
        drift("안정형", false),
        drift("배당형", true, 9.3),
      ]);
      renderCard();
      const toggle = await screen.findByRole("button", { name: /리밸런싱 필요 · 포트폴리오 2개/ });
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByText("성장형")).not.toBeInTheDocument();

      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute("aria-expanded", "true");
      const names = (await screen.findAllByText(/^(성장형|배당형)$/)).map((el) => el.textContent);
      expect(names).toEqual(["배당형", "성장형"]);
      expect(screen.queryByText("안정형")).not.toBeInTheDocument();
      expect(screen.getByText("배당형").closest("a")).toHaveAttribute(
        "href",
        "/rebalancing?rtab=%ED%8F%AC%ED%8A%B8%ED%8F%B4%EB%A6%AC%EC%98%A4&portfolioId=%EB%B0%B0%EB%8B%B9%ED%98%95",
      );
      expect(screen.getByText(/최대 9\.3%p · 2종목이 기준 5%p 초과/)).toBeInTheDocument();

      fireEvent.click(toggle);
      expect(screen.queryByText("배당형")).not.toBeInTheDocument();
    });

    it("drift-summary가 없으면 펼친 영역에 리밸런싱 탭 링크만", async () => {
      fetchActionItems.mockResolvedValue([rebalanceGroup]);
      renderCard();
      fireEvent.click(await screen.findByRole("button", { name: /리밸런싱 필요/ }));
      expect(screen.getByRole("link", { name: /리밸런싱 탭에서 보기/ })).toHaveAttribute(
        "href",
        "/rebalancing",
      );
    });
  });
});
