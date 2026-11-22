import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Challenge } from "@/api/challenges";
import ChallengeCard from "@/components/invest/ChallengeCard";

function makeChallenge(
  progress: Partial<Challenge["progress"]> = {},
  deadline: string | null = "2026-06",
): Challenge {
  return {
    id: "c1",
    title: "매달 적립",
    challenge_type: "DEPOSIT",
    target_amount: null,
    target_pct: null,
    target_months: 6,
    account_id: null,
    start_month: "2026-01",
    deadline_month: deadline,
    reminder_enabled: true,
    status: "ACTIVE",
    completed_at: null,
    created_at: "2026-01-01T00:00:00Z",
    progress: {
      progress_pct: 50,
      current_streak: 3,
      longest_streak: 3,
      this_month_net_krw: 0,
      this_month_satisfied: false,
      this_month_target_met: false,
      current_value_krw: null,
      current_return_pct: null,
      months: [],
      ...progress,
    },
  };
}

const noop = vi.fn();

describe("ChallengeCard 마감월", () => {
  it("남은 개월 수를 보여 준다", () => {
    render(
      <ChallengeCard
        challenge={makeChallenge({ months_left: 2 })}
        onEdit={noop}
        onArchive={noop}
        onDelete={noop}
      />,
    );
    expect(screen.getByText(/2개월 남음/)).toBeInTheDocument();
    expect(screen.queryByText("기한 종료")).not.toBeInTheDocument();
  });

  it("마감이 지나면 기한 종료 배지를 보이고 이번 달 배지는 숨긴다", () => {
    render(
      <ChallengeCard
        challenge={makeChallenge({ is_expired: true, months_left: 0 })}
        onEdit={noop}
        onArchive={noop}
        onDelete={noop}
      />,
    );
    expect(screen.getByText("기한 종료")).toBeInTheDocument();
    expect(screen.queryByText(/이번 달 미완료/)).not.toBeInTheDocument();
    expect(screen.queryByText(/남음/)).not.toBeInTheDocument();
  });
});
