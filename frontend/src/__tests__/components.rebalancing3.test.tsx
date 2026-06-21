import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";

vi.mock("@/utils/format", () => ({
  fmtKrwPrice: vi.fn((n: number) => `${n.toLocaleString()}원`),
}));

vi.mock("@/components/rebalancing/RebalancingBadges", () => ({
  SideBadge: ({ isBuy }: { isBuy: boolean }) => <span>{isBuy ? "매수" : "매도"}</span>,
  StatusBadge: ({ status }: { status: string }) => <span>{status}</span>,
}));

import { CashSummaryBar } from "@/components/rebalancing/CashSummaryBar";
import { RebalancingResultSection } from "@/components/rebalancing/RebalancingResultSection";
import type { CashAnalysis } from "@/hooks/rebalancingExecution/types";
import type { ExecutionResult } from "@/api/rebalancing";

// ------- CashSummaryBar -------
describe("CashSummaryBar", () => {
  const baseAnalysis: CashAnalysis = {
    deposit: 1_000_000,
    isOrderableKnown: false,
    sellProceeds: null,
    totalAvailable: null,
    buyCost: null,
    surplus: null,
  };

  it("deposit이 null이면 아무것도 렌더링하지 않는다", () => {
    const { container } = render(
      <CashSummaryBar analysis={{ ...baseAnalysis, deposit: null }} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("isOrderableKnown=false일 때 '예수금' 레이블과 미체결 안내를 표시한다", () => {
    render(<CashSummaryBar analysis={baseAnalysis} />);
    expect(screen.getByText(/예수금/)).toBeDefined();
    expect(screen.getByText(/미체결 주문 시 차이 발생/)).toBeDefined();
  });

  it("isOrderableKnown=true일 때 '주문가능' 레이블을 표시한다", () => {
    render(<CashSummaryBar analysis={{ ...baseAnalysis, isOrderableKnown: true }} />);
    expect(screen.getByText(/주문가능/)).toBeDefined();
  });

  it("매도예상이 있을 때 매도 정보와 사용가능 금액을 표시한다", () => {
    render(
      <CashSummaryBar
        analysis={{
          ...baseAnalysis,
          sellProceeds: 500_000,
          totalAvailable: 1_500_000,
        }}
      />,
    );
    expect(screen.getByText(/매도예상/)).toBeDefined();
    expect(screen.getByText(/사용가능/)).toBeDefined();
  });

  it("매수필요가 있고 잉여금이 양수일 때 '여유' 표시", () => {
    render(
      <CashSummaryBar
        analysis={{
          ...baseAnalysis,
          buyCost: 800_000,
          surplus: 200_000,
        }}
      />,
    );
    expect(screen.getByText(/매수필요/)).toBeDefined();
    expect(screen.getByText(/여유/)).toBeDefined();
  });

  it("잉여금이 음수일 때 '부족' 표시", () => {
    render(
      <CashSummaryBar
        analysis={{
          ...baseAnalysis,
          buyCost: 1_200_000,
          surplus: -200_000,
        }}
      />,
    );
    expect(screen.getByText(/부족/)).toBeDefined();
  });
});

// ------- RebalancingResultSection -------
describe("RebalancingResultSection", () => {
  const mockOrder = {
    ticker: "005930",
    name: "삼성전자",
    market: "KOSPI",
    side: "BUY" as const,
    quantity: 10,
    status: "SUCCESS" as const,
    order_no: "ORD-001",
    error_msg: null,
    order_type: "MARKET",
  };

  const mockResult: ExecutionResult = {
    account_id: "acc-1",
    account_name: "테스트 계좌",
    is_mock: false,
    orders: [mockOrder],
    success_count: 1,
    fail_count: 0,
    executed_at: "2026-06-19T00:00:00",
  };

  it("results가 빈 배열이면 아무것도 렌더링하지 않는다", () => {
    const { container } = renderWithProviders(<RebalancingResultSection results={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("계좌명과 성공 건수를 표시한다", () => {
    renderWithProviders(<RebalancingResultSection results={[mockResult]} />);
    expect(screen.getByText("테스트 계좌")).toBeDefined();
    expect(screen.getByText(/1건 성공/)).toBeDefined();
  });

  it("is_mock=true이면 '모의투자' 뱃지를 표시한다", () => {
    renderWithProviders(<RebalancingResultSection results={[{ ...mockResult, is_mock: true }]} />);
    expect(screen.getByText("모의투자")).toBeDefined();
  });

  it("fail_count > 0이면 실패 건수를 표시한다", () => {
    renderWithProviders(
      <RebalancingResultSection results={[{ ...mockResult, success_count: 0, fail_count: 2 }]} />,
    );
    expect(screen.getByText(/2건 실패/)).toBeDefined();
  });

  it("주문 종목명과 티커를 표시한다", () => {
    renderWithProviders(<RebalancingResultSection results={[mockResult]} />);
    expect(screen.getAllByText("삼성전자").length).toBeGreaterThan(0);
    expect(screen.getAllByText("005930").length).toBeGreaterThan(0);
  });

  it("LIMIT 주문은 '지정가', MARKET 주문은 '시장가'로 표시한다", () => {
    const limitResult: ExecutionResult = {
      ...mockResult,
      orders: [{ ...mockOrder, order_type: "LIMIT" }],
    };
    renderWithProviders(<RebalancingResultSection results={[mockResult, limitResult]} />);
    expect(screen.getAllByText("시장가").length).toBeGreaterThan(0);
    expect(screen.getAllByText("지정가").length).toBeGreaterThan(0);
  });

  it("여러 계좌 결과를 모두 렌더링한다", () => {
    const result2: ExecutionResult = {
      ...mockResult,
      account_id: "acc-2",
      account_name: "두번째 계좌",
    };
    renderWithProviders(<RebalancingResultSection results={[mockResult, result2]} />);
    expect(screen.getByText("테스트 계좌")).toBeDefined();
    expect(screen.getByText("두번째 계좌")).toBeDefined();
  });

  it("order_no 없고 error_msg 있는 주문의 오류 메시지를 표시한다", () => {
    const failedResult: ExecutionResult = {
      ...mockResult,
      orders: [
        {
          ...mockOrder,
          status: "FAILED" as const,
          order_no: null,
          error_msg: "잔고 부족",
          order_type: "LIMIT",
        },
      ],
    };
    renderWithProviders(<RebalancingResultSection results={[failedResult]} />);
    expect(screen.getAllByText("잔고 부족").length).toBeGreaterThan(0);
  });
});
