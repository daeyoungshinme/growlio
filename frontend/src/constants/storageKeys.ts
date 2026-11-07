/** 사용자별 localStorage 키 — 같은 기기에서 다른 계정으로 로그인해도 서로의 상태가 번지지 않게 user id를 붙인다. */
import { storageRemove } from "@/utils/safeStorage";

/** 설정에서 푸시를 끈 기록(앱 재시작 시 자동 등록을 건너뜀, plans/117 C2). */
export const pushOptOutKey = (userId: string) => `growlio:push-opt-out:${userId}`;

/** 목표 마법사를 한 번 자동으로 띄웠는지(plans/117 C5 — 예전엔 기기 단위라 다음 계정에서 안 떴다). */
export const goalWizardShownKey = (userId: string) => `growlio:goal-wizard-auto-shown:${userId}`;

/** 홈 "기준 포트폴리오 만들기" 배너를 닫았는지(plans/118 C7 — 예전엔 기기 단위라 다음 계정에서 안 떴다). */
export const targetPortfolioBannerDismissedKey = (userId: string) =>
  `growlio:dashboard:target-portfolio-banner-dismissed:${userId}`;

/** 홈 "적립 챌린지 만들기" 카드를 닫았는지(plans/118 C7). */
export const challengeEmptyStateDismissedKey = (userId: string) =>
  `growlio:dashboard:challenge-empty-state-dismissed:${userId}`;

/** 탈퇴 시 지울 그 사용자의 키 목록. */
export const userScopedStorageKeys = (userId: string) => [
  pushOptOutKey(userId),
  goalWizardShownKey(userId),
  targetPortfolioBannerDismissedKey(userId),
  challengeEmptyStateDismissedKey(userId),
];

/** 사용자별 키로 옮기기 전 기기 단위 키 — 더는 읽지 않으므로 부팅 때 지운다. */
const LEGACY_DEVICE_KEYS = [
  "growlio:goal-wizard-auto-shown",
  "growlio:dashboard:target-portfolio-banner-dismissed",
  "growlio:dashboard:challenge-empty-state-dismissed",
];

export function removeLegacyDeviceKeys(): void {
  LEGACY_DEVICE_KEYS.forEach(storageRemove);
}
