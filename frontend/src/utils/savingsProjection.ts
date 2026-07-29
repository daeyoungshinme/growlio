/** 절약 복리 시뮬레이터 계산 유틸 — 월 절약액을 투자했을 때의 미래가치 계산 */

/**
 * 매달 절약해 투자하는 금액의 N년 후 미래가치 (월복리 연금 공식)
 * FV = pmt * (((1+r)^n - 1) / r), r = 월수익률, n = 총 개월수
 * 예: futureValueOfMonthlySavings(100_000, 7, 10) → 약 1,730만원
 */
export function futureValueOfMonthlySavings(
  monthlyAmount: number,
  annualReturnPct: number,
  years: number,
): number {
  const n = years * 12;
  if (n <= 0) return 0;
  const r = annualReturnPct / 100 / 12;
  if (r === 0) return monthlyAmount * n;
  return monthlyAmount * ((Math.pow(1 + r, n) - 1) / r);
}

/**
 * 목돈을 한 번에 투자했을 때 N년 후 미래가치 (월복리)
 * FV = principal * (1+r)^n, r = 월수익률, n = 총 개월수
 */
export function futureValueOfLumpSum(
  principal: number,
  annualReturnPct: number,
  years: number,
): number {
  const n = years * 12;
  if (n <= 0) return 0;
  const r = annualReturnPct / 100 / 12;
  return principal * Math.pow(1 + r, n);
}

export interface SavingsProjectionPoint {
  year: number;
  /** 단순 납입 누계 (복리 미반영) */
  principal: number;
  /** 복리 반영 미래가치 */
  value: number;
}

/**
 * 연도별 원금 누계 vs 복리 반영 미래가치 시리즈 (차트/스탯 타일용)
 */
export function buildSavingsProjectionSeries(
  monthlyAmount: number,
  annualReturnPct: number,
  years: number[] = [1, 5, 10, 20, 30],
): SavingsProjectionPoint[] {
  return years.map((year) => ({
    year,
    principal: monthlyAmount * 12 * year,
    value: futureValueOfMonthlySavings(monthlyAmount, annualReturnPct, year),
  }));
}

/**
 * 연도별 원금(추가 납입 없음) vs 복리 반영 미래가치 시리즈 — 거치식 투자용
 */
export function buildLumpSumProjectionSeries(
  principal: number,
  annualReturnPct: number,
  years: number[] = [1, 5, 10, 20, 30],
): SavingsProjectionPoint[] {
  return years.map((year) => ({
    year,
    principal,
    value: futureValueOfLumpSum(principal, annualReturnPct, year),
  }));
}
