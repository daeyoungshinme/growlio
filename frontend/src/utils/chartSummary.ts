/**
 * 차트 대체 텍스트(`role="img"`의 `aria-label`) — 화면에서 읽는 핵심 수치를 문장으로 만든다.
 * 금액을 숨기는 화면(홈 전체자산)의 차트에는 쓰지 않는다.
 */
import { fmtKrw } from "@/utils/format";

function signedPct(n: number): string {
  return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

/** 이름·비중 목록 → "A 40.0%, B 30.0%". `limit`을 넘는 항목은 개수만 알린다. */
export function summarizeWeights(
  label: string,
  items: readonly { name: string; pct: number }[],
  limit = 5,
): string {
  if (items.length === 0) return `${label}: 데이터 없음`;
  const sorted = [...items].sort((a, b) => b.pct - a.pct);
  const listed = sorted
    .slice(0, limit)
    .map((i) => `${i.name} ${i.pct.toFixed(1)}%`)
    .join(", ");
  const rest = sorted.length - limit;
  return `${label}: ${listed}${rest > 0 ? ` 외 ${rest}개` : ""}`;
}

/** 월·연도별 금액 → 합계·최고·최저. 배당이 없는 달도 사실이므로 0을 최저에서 빼지 않는다. */
export function summarizeAmounts(
  label: string,
  points: readonly { name: string; amount: number }[],
): string {
  const [first] = points;
  if (!first) return `${label}: 데이터 없음`;
  let max = first;
  let min = first;
  let total = 0;
  for (const p of points) {
    total += p.amount;
    if (p.amount > max.amount) max = p;
    if (p.amount < min.amount) min = p;
  }
  if (total === 0) return `${label}: 금액 없음`;
  return `${label}: 합계 ${fmtKrw(total)}, 최고 ${max.name} ${fmtKrw(max.amount)}, 최저 ${min.name} ${fmtKrw(min.amount)}`;
}

/** 월별 자산 구성(최신순) → 최신 달의 총액과 상위 항목. */
export function summarizeAllocationHistory(
  points: readonly {
    month: string;
    allocations: readonly { label: string; amount_krw: number }[];
  }[],
): string {
  const latest = points[0];
  if (!latest) return "자산 구성 추이 차트: 데이터 없음";
  const total = latest.allocations.reduce((s, a) => s + a.amount_krw, 0);
  const top = [...latest.allocations]
    .sort((a, b) => b.amount_krw - a.amount_krw)
    .slice(0, 3)
    .map((a) => `${a.label} ${fmtKrw(a.amount_krw)}`)
    .join(", ");
  return `자산 구성 추이 차트: ${points.length}개월, ${latest.month} 총 ${fmtKrw(total)}${top ? ` (${top})` : ""}`;
}

/** 적립 전망 → 마지막 실제 자산과 차트 끝 시점의 전망. */
export function summarizeProjection(
  points: readonly { month: string; actual_krw: number | null; projected_krw: number }[],
): string {
  const last = points[points.length - 1];
  if (!last) return "자산 전망 차트: 데이터 없음";
  const lastActual = [...points].reverse().find((p) => p.actual_krw !== null);
  const actual = lastActual
    ? `${lastActual.month} 실제 자산 ${fmtKrw(lastActual.actual_krw ?? 0)}`
    : "실제 자산 없음";
  return `자산 전망 차트: ${actual}, ${last.month} 전망 ${fmtKrw(last.projected_krw)}`;
}

/** 복리 시뮬레이션 → 마지막 해의 평가액과 원금. */
export function summarizeSavings(years: number, value: number, principal: number): string {
  return `복리 시뮬레이션 차트: ${years}년 뒤 ${fmtKrw(value)}, 투자 원금 ${fmtKrw(principal)}`;
}

type BacktestSeries = { name: string; values: readonly (number | null)[] };

/** 백테스트 → 전략별 최종 수익률. `values`는 기준 100 지수다 — 툴팁과 같이 100을 뺀다. */
export function summarizeBacktestCumulative(series: readonly BacktestSeries[]): string {
  const parts = series.flatMap((s) => {
    const last = [...s.values].reverse().find((v) => v != null);
    return last == null ? [] : [`${s.name} ${signedPct(last - 100)}`];
  });
  return `누적 수익 차트: ${parts.join(", ") || "데이터 없음"}`;
}

/** 백테스트 → 전략별 최고·최저 연도. */
export function summarizeBacktestAnnual(
  series: readonly { name: string }[],
  rows: readonly ({ year: string } & Record<string, string | number | null>)[],
): string {
  const parts = series.flatMap((s) => {
    let best: { year: string; v: number } | null = null;
    let worst: { year: string; v: number } | null = null;
    for (const r of rows) {
      const v = r[s.name];
      if (typeof v !== "number") continue;
      if (!best || v > best.v) best = { year: r.year, v };
      if (!worst || v < worst.v) worst = { year: r.year, v };
    }
    if (!best || !worst) return [];
    return [
      `${s.name} 최고 ${best.year}년 ${signedPct(best.v)}, 최저 ${worst.year}년 ${signedPct(worst.v)}`,
    ];
  });
  return `연도별 수익률 차트: ${parts.join(" / ") || "데이터 없음"}`;
}

/** 백테스트 → 전략별 최대 낙폭. `values`는 차트가 이미 계산한 낙폭(%) 시계열이다. */
export function summarizeBacktestDrawdown(series: readonly BacktestSeries[]): string {
  const parts = series.flatMap((s) => {
    const nums = s.values.filter((v): v is number => v != null);
    return nums.length ? [`${s.name} ${signedPct(nums.reduce((m, v) => Math.min(m, v)))}`] : [];
  });
  return `최대 낙폭 차트: ${parts.join(", ") || "데이터 없음"}`;
}
