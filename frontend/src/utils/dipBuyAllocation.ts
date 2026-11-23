/**
 * 낙폭 추매 규칙 배분 — 새 배분을 넣으려고 다른 규칙 배분을 비율대로 줄인다(합계가 100을 넘을 때만).
 * 백엔드 `dip_buy_calculator.shrink_allocations`와 같은 규칙: 소수 둘째 자리 내림, 각 규칙 1% 이상, 안 되면 null.
 */
export function shrinkAllocations(others: readonly number[], newPct: number): number[] | null {
  const total = others.reduce((sum, a) => sum + a, 0);
  if (total + newPct <= 100 + 1e-9) return [...others];
  const available = 100 - newPct;
  if (available < others.length) return null;
  const shrunk = others.map((a) => Math.floor(((a * available) / total) * 100) / 100);
  return shrunk.some((a) => a < 1) ? null : shrunk;
}
