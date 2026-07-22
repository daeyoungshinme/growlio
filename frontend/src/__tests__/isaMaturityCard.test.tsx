import { describe, it, expect, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { IsaAccountStatus, IsaStatusSummary } from "@/api/tax";

const fetchIsaStatus = vi.fn();
const updateIsaPnlOverride = vi.fn();
const toastMock = vi.fn();

vi.mock("@/api/tax", () => ({
  fetchIsaStatus: (...args: unknown[]) => fetchIsaStatus(...args),
}));

vi.mock("@/api/assets", () => ({
  updateIsaPnlOverride: (...args: unknown[]) => updateIsaPnlOverride(...args),
}));

vi.mock("@/utils/toast", () => ({ toast: (...args: unknown[]) => toastMock(...args) }));

import IsaMaturityCard from "@/components/dashboard/IsaMaturityCard";

function makeStatus(overrides: Partial<IsaAccountStatus> = {}): IsaAccountStatus {
  return {
    account_id: "acc1",
    account_name: "일반형 ISA",
    isa_type: "GENERAL",
    isa_open_date: "2023-01-01",
    maturity_date: "2026-01-01",
    is_mature: true,
    days_remaining: 0,
    needs_open_date: false,
    estimated_cumulative_pnl_krw: 3_000_000,
    is_manual_override: false,
    tax_free_limit_krw: 2_000_000,
    taxable_excess_krw: 1_000_000,
    estimated_tax_krw: 99_000,
    ...overrides,
  };
}

function makeSummary(accounts: IsaAccountStatus[]): IsaStatusSummary {
  return { accounts, note: "추정치입니다." };
}

describe("IsaMaturityCard", () => {
  it("ISA 계좌가 없으면 렌더링하지 않는다", async () => {
    fetchIsaStatus.mockResolvedValue(makeSummary([]));
    const { container } = renderWithProviders(<IsaMaturityCard />);
    await waitFor(() => expect(fetchIsaStatus).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("의무가입 충족 배지와 한도 초과 세금 경고를 표시한다", async () => {
    fetchIsaStatus.mockResolvedValue(makeSummary([makeStatus()]));
    renderWithProviders(<IsaMaturityCard />);
    await waitFor(() => expect(screen.getByText("의무가입 충족")).toBeInTheDocument());
    expect(screen.getByText(/한도 초과/)).toBeInTheDocument();
  });

  it("가입일이 없으면 안내 배지를 표시한다", async () => {
    fetchIsaStatus.mockResolvedValue(
      makeSummary([makeStatus({ needs_open_date: true, maturity_date: null, is_mature: false })]),
    );
    renderWithProviders(<IsaMaturityCard />);
    await waitFor(() => expect(screen.getByText("가입일 미입력")).toBeInTheDocument());
  });

  it("직접 입력으로 누적손익을 저장할 수 있다", async () => {
    fetchIsaStatus.mockResolvedValue(makeSummary([makeStatus()]));
    updateIsaPnlOverride.mockResolvedValue({});
    renderWithProviders(<IsaMaturityCard />);
    await waitFor(() => expect(screen.getByText("직접 입력")).toBeInTheDocument());

    fireEvent.click(screen.getByText("직접 입력"));
    const input = screen.getByPlaceholderText("누적손익(원)");
    fireEvent.change(input, { target: { value: "5000000" } });
    expect(screen.getByText("5,000,000원 (500만원)")).toBeInTheDocument();
    fireEvent.click(screen.getByText("저장"));

    await waitFor(() => expect(updateIsaPnlOverride).toHaveBeenCalledWith("acc1", 5_000_000));
  });

  it("수동 입력값이 있으면 자동 추정 되돌리기 버튼을 표시한다", async () => {
    fetchIsaStatus.mockResolvedValue(makeSummary([makeStatus({ is_manual_override: true })]));
    renderWithProviders(<IsaMaturityCard />);
    await waitFor(() => expect(screen.getByText("자동 추정으로 되돌리기")).toBeInTheDocument());
  });

  it("embedded 모드에서는 카드 헤더/보더 없이 내용만 렌더한다", async () => {
    fetchIsaStatus.mockResolvedValue(makeSummary([makeStatus()]));
    const { container } = renderWithProviders(<IsaMaturityCard embedded />);
    await waitFor(() => expect(screen.getByText("ISA 만기·세제 현황")).toBeInTheDocument());
    expect(container.querySelector(".card")).toBeNull();
  });
});
