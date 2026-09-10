import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders as renderWithProvidersBase } from "@/test/renderWithProviders";
import type { Challenge } from "@/api/challenges";

const fetchChallenges = vi.fn();
const fetchAccounts = vi.fn();
const createChallenge = vi.fn();
const updateChallenge = vi.fn();
const deleteChallenge = vi.fn();
const toastMock = vi.fn();

vi.mock("@/api/challenges", () => ({
  fetchChallenges: (...a: unknown[]) => fetchChallenges(...a),
  fetchChallengeSummary: vi.fn(),
  createChallenge: (...a: unknown[]) => createChallenge(...a),
  updateChallenge: (...a: unknown[]) => updateChallenge(...a),
  deleteChallenge: (...a: unknown[]) => deleteChallenge(...a),
}));
vi.mock("@/api/assets", () => ({ fetchAccounts: (...a: unknown[]) => fetchAccounts(...a) }));
vi.mock("@/utils/toast", () => ({ toast: (...a: unknown[]) => toastMock(...a) }));
vi.mock("@/utils/queryInvalidation", () => ({
  invalidateChallengeData: vi.fn(),
}));

import ChallengeSection from "@/components/invest/ChallengeSection";

function render(ui: React.ReactElement) {
  return renderWithProvidersBase(<MemoryRouter>{ui}</MemoryRouter>);
}

function makeChallenge(overrides: Partial<Challenge> = {}): Challenge {
  return {
    id: "c1",
    title: "매달 50만원 적립",
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
      longest_streak: 3,
      this_month_net_krw: 0,
      this_month_satisfied: false,
      this_month_target_met: false,
      current_value_krw: null,
      current_return_pct: null,
      months: [
        { month: "2026-01", net_krw: 500000, satisfied: true, target_met: true },
        { month: "2026-02", net_krw: 500000, satisfied: true, target_met: true },
      ],
    },
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchAccounts.mockResolvedValue([]);
});

describe("ChallengeSection", () => {
  it("shows empty state when no challenges", async () => {
    fetchChallenges.mockResolvedValue([]);
    render(<ChallengeSection />);
    await waitFor(() => expect(screen.getByText("아직 만든 챌린지가 없어요")).toBeInTheDocument());
  });

  it("renders a challenge card with streak", async () => {
    fetchChallenges.mockResolvedValue([makeChallenge()]);
    render(<ChallengeSection />);
    await waitFor(() => expect(screen.getByText("매달 50만원 적립")).toBeInTheDocument());
    expect(screen.getByText("3개월 연속")).toBeInTheDocument();
    expect(screen.getByText("이번 달 미완료")).toBeInTheDocument();
  });

  it("opens create modal on button click", async () => {
    fetchChallenges.mockResolvedValue([]);
    render(<ChallengeSection />);
    await waitFor(() => screen.getByText("아직 만든 챌린지가 없어요"));
    fireEvent.click(screen.getByRole("button", { name: /새 챌린지/ }));
    expect(await screen.findByRole("button", { name: "만들기" })).toBeInTheDocument();
    expect(screen.getByText("유형")).toBeInTheDocument();
  });
});
