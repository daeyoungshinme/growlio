/** 사용자별 localStorage 키 — 같은 기기에서 다른 계정으로 로그인해도 서로의 상태가 번지지 않게 user id를 붙인다. */

/** 설정에서 푸시를 끈 기록(앱 재시작 시 자동 등록을 건너뜀, plans/117 C2). */
export const pushOptOutKey = (userId: string) => `growlio:push-opt-out:${userId}`;

/** 목표 마법사를 한 번 자동으로 띄웠는지(plans/117 C5 — 예전엔 기기 단위라 다음 계정에서 안 떴다). */
export const goalWizardShownKey = (userId: string) => `growlio:goal-wizard-auto-shown:${userId}`;

/** 탈퇴 시 지울 그 사용자의 키 목록. */
export const userScopedStorageKeys = (userId: string) => [
  pushOptOutKey(userId),
  goalWizardShownKey(userId),
];
