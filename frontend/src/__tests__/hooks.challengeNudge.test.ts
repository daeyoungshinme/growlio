import { describe, expect, it } from "vitest";
import type { Challenge } from "@/api/challenges";
import { CHALLENGE_NUDGE_DAY_OF_MONTH, challengeNeedsAttention } from "@/hooks/useChallengeNudge";

function challenge(
  overrides: Partial<Challenge> = {},
  progress: Partial<Challenge["progress"]> = {},
) {
  return {
    id: "c1",
    challenge_type: "DEPOSIT",
    status: "ACTIVE",
    reminder_enabled: true,
    ...overrides,
    progress: { this_month_satisfied: false, is_expired: false, ...progress },
  } as Challenge;
}

/** 백엔드 get_challenge_summary와 같은 판정(plans/151 B4) */
describe("challengeNeedsAttention", () => {
  const late = CHALLENGE_NUDGE_DAY_OF_MONTH;

  it("20일 전에는 항상 배지 없음", () => {
    expect(challengeNeedsAttention([challenge()], late - 1)).toBe(false);
  });

  it("이번 달 순입금이 없는 알림 켠 활성 입금 챌린지면 배지", () => {
    expect(challengeNeedsAttention([challenge()], late)).toBe(true);
  });

  it("입금했거나·알림 끔·기한 종료·완료·입금 외 유형은 세지 않는다", () => {
    const excluded = [
      challenge({}, { this_month_satisfied: true }),
      challenge({ reminder_enabled: false }),
      challenge({}, { is_expired: true }),
      challenge({ status: "COMPLETED" }),
      challenge({ challenge_type: "RETURN_PCT" }),
    ];
    expect(challengeNeedsAttention(excluded, late)).toBe(false);
  });
});
