import { monthlyRate } from "@/utils/savingsProjection";

/**
 * DCA 프로젝션 시나리오 비교 계산 유틸.
 * backend/app/services/dca_service.py의 _build_projection_curve()와 동일한 공식을 그대로 포팅 —
 * 백엔드 재조회 없이 이미 받은 이론 복리 곡선(n=0 지점)을 시작값으로 재사용한다.
 */
import type { DCAProjectionPoint } from "@/api/invest";

/**
 * n=0 시점의 이론값(=초기 투자금)에서 매달 pmt를 적립하며 연 annualReturnPct로 복리 성장했을 때의
 * n개월 후 이론값. r=0(수익률 0%)이면 원금 단순 합산.
 */
export function projectedValueAtMonth(
  initial: number,
  monthlyDepositAmount: number,
  annualReturnPct: number,
  n: number,
): number {
  const r = monthlyRate(annualReturnPct);
  if (r === 0) return initial + monthlyDepositAmount * n;
  return initial * Math.pow(1 + r, n) + monthlyDepositAmount * ((Math.pow(1 + r, n) - 1) / r);
}

/**
 * points(월별 이론값 배열, 인덱스=시작일로부터의 개월수)를 기준으로 다른 가정 수익률의 곡선을 계산.
 * 반환값은 month 문자열(예: "2026-08") → 이론값 맵.
 */
export function buildScenarioCurve(
  points: DCAProjectionPoint[],
  monthlyDepositAmount: number,
  annualReturnPct: number,
): Record<string, number> {
  const first = points[0];
  if (!first) return {};
  const initial = first.projected_krw;
  const result: Record<string, number> = {};
  points.forEach((point, n) => {
    result[point.month] = projectedValueAtMonth(initial, monthlyDepositAmount, annualReturnPct, n);
  });
  return result;
}

/** 시나리오 비교 폭 — 목표 수익률 ±3%p(보수 4·중립 7·공격 10% 프리셋과 같은 간격) */
export const SCENARIO_SPREAD_PCT = 3;
/** 목표 도달 탐색 상한(50년) — 백엔드 `dca_service`의 600개월과 같다 */
const MAX_GOAL_MONTHS = 600;

/** 목표 수익률 기준 보수·공격 가정 수익률(보수는 0% 하한). 목표 수익률이 없으면 null. */
export function scenarioReturns(
  goalAnnualReturnPct: number | null | undefined,
): { conservative: number; base: number; aggressive: number } | null {
  if (goalAnnualReturnPct == null) return null;
  return {
    conservative: Math.max(0, goalAnnualReturnPct - SCENARIO_SPREAD_PCT),
    base: goalAnnualReturnPct,
    aggressive: goalAnnualReturnPct + SCENARIO_SPREAD_PCT,
  };
}

/**
 * 시작값·월 적립·연 수익률로 목표 금액에 처음 닿는 개월 수(시작 시점 0). 600개월 안에 못 닿으면 null.
 */
export function monthsToReachGoal(
  initial: number,
  monthlyDepositAmount: number,
  annualReturnPct: number,
  goalAmount: number,
): number | null {
  for (let n = 0; n <= MAX_GOAL_MONTHS; n++) {
    if (projectedValueAtMonth(initial, monthlyDepositAmount, annualReturnPct, n) >= goalAmount)
      return n;
  }
  return null;
}

/** "YYYY-MM"에서 n개월 뒤 "YYYY-MM" — 타임존 영향 없이 문자열로 계산 */
export function monthAfter(startMonth: string, n: number): string {
  const [y, m] = startMonth.split("-").map(Number) as [number, number];
  const idx = y * 12 + (m - 1) + n;
  return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, "0")}`;
}
