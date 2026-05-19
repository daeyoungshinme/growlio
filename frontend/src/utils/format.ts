/** 공유 포맷팅 유틸리티 — 금액, 날짜, 퍼센트 표기 */

/**
 * 금액을 억원/만원/원 단위로 변환 (음수 지원)
 * 예: 150_000_000 → "1.50억원", 50_000 → "5만원", 3_000 → "3,000원"
 */
export function fmtKrw(n: number): string {
  if (Math.abs(n) >= 1e8) return `${(n / 1e8).toFixed(2)}억원`;
  if (Math.abs(n) >= 1e4) return `${Math.round(n / 1e4).toLocaleString()}만원`;
  return `${n.toLocaleString()}원`;
}

/**
 * null/undefined를 허용하는 금액 포맷 — null이면 "—" 반환
 */
export function fmtKrwNullable(n: number | null | undefined): string {
  if (n == null) return "—";
  return fmtKrw(n);
}

/**
 * 차트 레이블용 간략 포맷 (단위 없이 짧게)
 * 예: 150_000_000 → "1.5억", 50_000 → "5만"
 */
export function fmtKrwShort(n: number): string {
  if (Math.abs(n) >= 1e8) return `${(n / 1e8).toFixed(1)}억`;
  if (Math.abs(n) >= 1e4) return `${Math.round(n / 1e4).toLocaleString()}만`;
  return `${n.toLocaleString()}`;
}

/**
 * "YYYY-MM" 형식을 "YYYY년 M월"로 변환
 * 예: "2025-05" → "2025년 5월"
 */
export function fmtMonth(monthStr: string): string {
  const [year, month] = monthStr.split("-").map(Number);
  return `${year}년 ${month}월`;
}

/**
 * 퍼센트 포맷 (양수는 "+" 접두사 포함)
 * 예: 5.23 → "+5.23%", -3.1 → "-3.10%"
 */
export function fmtPct(n: number | null, digits = 2): string {
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
}
