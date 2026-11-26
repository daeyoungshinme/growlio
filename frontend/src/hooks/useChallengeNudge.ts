import { useMemo } from "react";
import type { Challenge } from "@/api/challenges";
import { useChallenges } from "@/hooks/useChallenges";
import { localToday } from "@/utils/format";

/** 이 날짜부터 "이번 달 아직 적립 안 함"을 배지로 — 백엔드 `challenge_service._NUDGE_DAY_OF_MONTH`와 같게 */
export const CHALLENGE_NUDGE_DAY_OF_MONTH = 20;

/**
 * 이번 달 순입금이 없는 알림 켠 활성 입금 챌린지가 있는지 — 백엔드 `get_challenge_summary`와 같은 판정을
 * 이미 받아 둔 챌린지 목록(`progress.this_month_satisfied` = 순입금 > 0)으로 한다. 내비는 모든 화면에 떠 있어
 * 예전엔 부팅마다 목록을 받은 뒤 `/challenges/summary`를 한 번 더 불렀다(plans/151 B4).
 */
export function challengeNeedsAttention(
  challenges: readonly Challenge[],
  dayOfMonth: number,
): boolean {
  if (dayOfMonth < CHALLENGE_NUDGE_DAY_OF_MONTH) return false;
  return challenges.some(
    (c) =>
      c.status === "ACTIVE" &&
      c.challenge_type === "DEPOSIT" &&
      c.reminder_enabled &&
      !c.progress.is_expired &&
      !c.progress.this_month_satisfied,
  );
}

/** 하단 내비·사이드바 배지용 — 추가 요청 없이 챌린지 목록 캐시로 판정 */
export function useChallengeNudge(): boolean {
  const { data: challenges } = useChallenges();
  // 날짜는 렌더마다 읽어 deps에 넣는다 — 목록 참조만 보면 앱을 켜 둔 채 20일이 돼도 배지가 안 뜬다
  const dayOfMonth = Number(localToday().slice(8, 10));
  return useMemo(
    () => challengeNeedsAttention(challenges ?? [], dayOfMonth),
    [challenges, dayOfMonth],
  );
}
