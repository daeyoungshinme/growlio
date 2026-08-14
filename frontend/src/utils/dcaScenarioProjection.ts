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
  const r = annualReturnPct / 100 / 12;
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
  if (points.length === 0) return {};
  const initial = points[0].projected_krw;
  const result: Record<string, number> = {};
  points.forEach((point, n) => {
    result[point.month] = projectedValueAtMonth(initial, monthlyDepositAmount, annualReturnPct, n);
  });
  return result;
}
