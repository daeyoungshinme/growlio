import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { Challenge } from "@/api/challenges";
import ChallengeProgressCard from "@/components/dashboard/ChallengeProgressCard";

function makeChallenge(overrides: Partial<Challenge> = {}): Challenge {
  return {
    id: "c1",
    title: "매달 50만원",
    challenge_type: "DEPOSIT",
    target_amount: 500000,
    target_pct: null,
    target_months: 12,
    account_id: null,
    start_month: "2026-01",
    deadline_month: null,
    reminder_enabled: true,
    status: "ACTIVE",
    completed_at: null,
    created_at: "2026-01-01T00:00:00Z",
    progress: {
      progress_pct: 25,
      current_streak: 3,
      longest_streak: 4,
      this_month_net_krw: 500000,
      this_month_satisfied: true,
      this_month_target_met: true,
      current_value_krw: null,
      current_return_pct: null,
      months: [],
    },
    ...overrides,
  };
}

function render(ui: React.ReactElement) {
  return renderWithProviders(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("ChallengeProgressCard", () => {
  it("renders nothing when no active challenges", () => {
    const { container } = render(
      <ChallengeProgressCard challenges={[makeChallenge({ status: "COMPLETED" })]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows streak and this-month status for deposit challenge", () => {
    render(<ChallengeProgressCard challenges={[makeChallenge()]} />);
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("이번 달 완료")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/invest-plan?tab=챌린지");
  });

  it("counts extra active challenges", () => {
    render(
      <ChallengeProgressCard
        challenges={[makeChallenge(), makeChallenge({ id: "c2", title: "수익률" })]}
      />,
    );
    expect(screen.getByText(/외 1개/)).toBeInTheDocument();
  });
});
