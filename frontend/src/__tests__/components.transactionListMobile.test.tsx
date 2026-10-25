import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { TransactionList } from "@/components/assets/TransactionList";
import type { Transaction } from "@/api/transactions";

function mockViewport(smUp: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: smUp,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

const txs = Array.from({ length: 120 }, (_, i) => ({
  id: `t${i}`,
  transaction_type: "DEPOSIT",
  amount: 1000 + i,
  transaction_date: "2026-01-01",
  ticker: null,
  notes: null,
})) as unknown as Transaction[];

describe("TransactionList 모바일", () => {
  const original = window.matchMedia;
  beforeEach(() => mockViewport(false));
  afterEach(() => {
    window.matchMedia = original;
  });

  it("모바일에선 데스크톱 표를 그리지 않고 카드를 50건씩 나눠 그린다", () => {
    const { container } = render(
      <TransactionList
        txList={txs}
        isLoading={false}
        activeType="DEPOSIT"
        isDeleting={false}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(container.querySelector("table")).toBeNull();
    expect(screen.getAllByLabelText("수정")).toHaveLength(50);

    fireEvent.click(screen.getByText("더 보기 (70건 남음)"));
    expect(screen.getAllByLabelText("수정")).toHaveLength(100);
  });

  it("데스크톱에선 모바일 카드를 그리지 않는다", () => {
    mockViewport(true);
    const { container } = render(
      <TransactionList
        txList={txs}
        isLoading={false}
        activeType="DEPOSIT"
        isDeleting={false}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(container.querySelector("table")).not.toBeNull();
    expect(screen.queryByText(/더 보기/)).toBeNull();
  });
});
