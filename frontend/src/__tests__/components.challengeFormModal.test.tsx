import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import ChallengeFormModal from "@/components/invest/ChallengeFormModal";
import type { Challenge } from "@/api/challenges";
import type { SettingsData } from "@/api/settings";

const settings = {
  monthly_deposit_amount: 500_000,
  goal_amount: 300_000_000,
  goal_annual_return_pct: 8,
} as SettingsData;

function renderModal(props: Partial<Parameters<typeof ChallengeFormModal>[0]> = {}) {
  const onSubmit = vi.fn();
  render(
    <ChallengeFormModal
      accounts={[]}
      settings={settings}
      submitting={false}
      onClose={vi.fn()}
      onSubmit={onSubmit}
      {...props}
    />,
  );
  return { onSubmit };
}

const monthlyInput = () => screen.getByLabelText(/월 목표액/) as HTMLInputElement;

describe("ChallengeFormModal — 매달 적립 금액은 적립 계획 월 적립액이 기본값 (docs/plans/50 M6)", () => {
  it("새 매달 적립 챌린지는 적립 계획의 월 적립액으로 시작하고, 그 사실을 안내한다", () => {
    renderModal();
    expect(monthlyInput().value).toBe("500000");
    expect(screen.getByText(/적립 계획의 월 적립액\(50만원\)을 쓰고 있어요/)).toBeInTheDocument();
    expect(screen.queryByText("적립 계획 금액으로 되돌리기")).not.toBeInTheDocument();
  });

  it("금액을 바꾸면 되돌리기 버튼이 생기고, 누르면 월 적립액으로 돌아간다", () => {
    renderModal();
    fireEvent.change(monthlyInput(), { target: { value: "300000" } });
    expect(screen.getByText("비워두면 매달 입금만 해도 달성으로 인정돼요")).toBeInTheDocument();

    fireEvent.click(screen.getByText("적립 계획 금액으로 되돌리기"));
    expect(monthlyInput().value).toBe("500000");
  });

  it("금액을 비우면 null로 저장된다 (입금만 해도 달성)", () => {
    const { onSubmit } = renderModal();
    fireEvent.change(screen.getByLabelText(/제목/), { target: { value: "매달 적립" } });
    fireEvent.change(monthlyInput(), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "만들기" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ target_amount: null }));
  });

  it("평가금액 유형으로 바꾸면 월 적립 기본값이 목표 평가금액으로 넘어가지 않는다", () => {
    renderModal();
    fireEvent.click(screen.getByRole("button", { name: "평가금액" }));
    expect((screen.getByLabelText(/목표 평가금액/) as HTMLInputElement).value).toBe("");

    fireEvent.click(screen.getByRole("button", { name: "매달 적립" }));
    expect(monthlyInput().value).toBe("500000");
  });

  it("편집 모드는 저장된 값을 유지한다 (월 목표액이 없던 챌린지에 기본값을 채우지 않음)", () => {
    const challenge = {
      id: "c1",
      title: "기존",
      challenge_type: "DEPOSIT",
      target_amount: null,
      target_pct: null,
      target_months: 12,
      account_id: null,
      start_month: "2026-01",
      deadline_month: null,
      reminder_enabled: true,
      status: "ACTIVE",
    } as unknown as Challenge;
    renderModal({ challenge });
    expect(monthlyInput().value).toBe("");
  });

  it("월 적립액이 미설정이면 빈 칸으로 시작한다", () => {
    renderModal({ settings: { ...settings, monthly_deposit_amount: null } });
    expect(monthlyInput().value).toBe("");
    expect(screen.getByText("비워두면 매달 입금만 해도 달성으로 인정돼요")).toBeInTheDocument();
  });
});
