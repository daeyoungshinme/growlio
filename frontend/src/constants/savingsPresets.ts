/** 절약 복리 시뮬레이터 프리셋 (SavingsSimulatorCard 전용) */

export interface SavingsReturnPreset {
  pct: number;
  label: string;
}

/**
 * 보수/중립/공격 가정 수익률.
 * 백엔드 goal_return_solver.py의 DEPOSIT_GUIDE_PRESET_RETURNS_PCT(4.0, 7.0, 10.0)와 동일한 값을
 * 프론트에 미러링한 것 — 이 시뮬레이터는 순수 클라이언트 계산이라 API로 값을 가져올 수 없음.
 * 백엔드 값이 바뀌면 이 상수도 함께 갱신할 것.
 */
export const SAVINGS_RETURN_PRESETS: SavingsReturnPreset[] = [
  { pct: 4, label: "보수적" },
  { pct: 7, label: "중립" },
  { pct: 10, label: "공격적" },
];

export const DEFAULT_SAVINGS_RETURN_PCT = 7;

export interface SavingsAmountPreset {
  amount: number;
  label: string;
}

/** 절약 동기부여용 금액 프리셋 칩 */
export const SAVINGS_AMOUNT_PRESETS: SavingsAmountPreset[] = [
  { amount: 30_000, label: "구독 서비스 정리" },
  { amount: 90_000, label: "커피값 아끼기" },
  { amount: 150_000, label: "배달음식 줄이기" },
];

export const DEFAULT_SAVINGS_MONTHLY_AMOUNT = 100_000;

export interface SavingsLumpSumPreset {
  amount: number;
  label: string;
}

/** 거치식 투자 동기부여용 금액 프리셋 칩 */
export const SAVINGS_LUMP_SUM_PRESETS: SavingsLumpSumPreset[] = [
  { amount: 1_000_000, label: "보너스" },
  { amount: 3_000_000, label: "적금 만기금" },
  { amount: 10_000_000, label: "목돈 여유자금" },
];

export const DEFAULT_SAVINGS_LUMP_SUM_AMOUNT = 3_000_000;
