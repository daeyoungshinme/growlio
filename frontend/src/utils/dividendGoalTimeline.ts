/** 목표 도달 탐색 상한(50년) — 적립 계획(`dca_service`)과 같은 600개월 */
const MAX_MONTHS = 600;

export interface DividendGoalProjection {
  /** 지금부터 목표 연배당에 닿는 개월 수(이미 달성이면 0). 50년 안에 못 닿으면 null */
  months: number | null;
  /** 가정한 배당수익률(%) */
  yieldPct: number;
}

/**
 * 배당 목표 달성 예상 — 현재 배당수익률이 그대로이고, 매달 적립액을 넣고 받은 배당을 재투자한다고 가정한다.
 * 주가 상승은 넣지 않지만(보수적) 배당은 세전 전액 재투자라 그만큼은 낙관적이다 — 화면 문구에 둘 다 밝힌다.
 * 투자자산이나 배당수익률이 0이면 계산하지 않는다(null).
 */
export function projectDividendGoal(
  investableAssetsKrw: number,
  estimatedAnnualDividendKrw: number,
  annualDividendGoalKrw: number,
  monthlyDepositKrw: number | null | undefined,
): DividendGoalProjection | null {
  if (investableAssetsKrw <= 0 || estimatedAnnualDividendKrw <= 0 || annualDividendGoalKrw <= 0)
    return null;
  const yieldRate = estimatedAnnualDividendKrw / investableAssetsKrw;
  const yieldPct = Math.round(yieldRate * 10_000) / 100;
  const deposit = Math.max(0, monthlyDepositKrw ?? 0);
  let assets = investableAssetsKrw;
  for (let n = 0; n <= MAX_MONTHS; n++) {
    if (assets * yieldRate >= annualDividendGoalKrw) return { months: n, yieldPct };
    assets += deposit + (assets * yieldRate) / 12;
  }
  return { months: null, yieldPct };
}
