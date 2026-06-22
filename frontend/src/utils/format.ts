/** 공유 포맷팅 유틸리티 — 금액, 날짜, 퍼센트 표기 */

/**
 * 금액을 억원/만원/원 단위로 변환 (음수 지원)
 * 예: 150_000_000 → "1.50억원", 50_000 → "5만원", 3_000 → "3,000원"
 */
export function fmtKrw(n: number): string {
  if (Math.abs(n) >= 1e8) return `${(n / 1e8).toFixed(2)}억원`;
  if (Math.abs(n) >= 1e4) return `${Math.round(n / 1e4).toLocaleString()}만원`;
  return `${Math.floor(n).toLocaleString()}원`;
}

/**
 * 주가 표시용 — 만원/억원 축약 없이 원 단위 그대로 표시
 * 예: 20_000 → "20,000원", 150_000 → "150,000원"
 */
export function fmtKrwPrice(n: number): string {
  return `${Math.floor(n).toLocaleString()}원`;
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
  return `${Math.floor(n).toLocaleString()}`;
}

/**
 * USD → KRW 환산 (반올림). rate가 없으면 0 반환.
 * 예: convertUsdToKrw(100, 1350) → 135000
 */
export function convertUsdToKrw(
  usd: number | null | undefined,
  rate: number | null | undefined,
): number {
  if (!usd || !rate) return 0;
  return Math.round(usd * rate);
}

/**
 * USD → KRW 환산 후 포맷. rate가 없으면 null 반환.
 * 예: formatUsdAsKrw(100, 1350) → "≈ ₩135,000"
 */
export function formatUsdAsKrw(
  usd: number | null | undefined,
  rate: number | null | undefined,
): string | null {
  const krw = convertUsdToKrw(usd, rate);
  if (!krw) return null;
  return `≈ ₩${krw.toLocaleString()}`;
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

/**
 * ISO 날짜 문자열을 현재 시각 기준 상대 시간으로 변환
 * 예: "3일 전", "오늘", "1시간 전"
 */
export function relativeTime(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  const diffHr = Math.floor(diffMs / 3_600_000);
  const diffDay = Math.floor(diffMs / 86_400_000);
  if (diffDay >= 30) {
    const diffMonth = Math.floor(diffDay / 30);
    return `${diffMonth}개월 전`;
  }
  if (diffDay >= 1) return `${diffDay}일 전`;
  if (diffHr >= 1) return `${diffHr}시간 전`;
  if (diffMin >= 1) return `${diffMin}분 전`;
  return "방금 전";
}
