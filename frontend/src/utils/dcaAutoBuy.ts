import type { RebalancingAlert } from "@/api/alerts";
import { isOverseasMarket } from "@/constants/markets";

/** 리밸런싱 알림 설정이 "정기 적립식 자동매수" 형태(매월 특정일 · 무조건 실행 · 자동 · 매수만)와
 * 일치하는지 판정한다. threshold_pct는 사용자가 나중에 손으로 조정했을 수 있어 비교 대상에서
 * 제외한다 — 나머지 4개 필드가 이 조합이면 화면에는 "정기 적립식 자동매수"로 보여준다. */
export function isDcaAutoBuyPreset(alert: RebalancingAlert | null | undefined): boolean {
  if (!alert) return false;
  return (
    alert.schedule_type === "MONTHLY" &&
    alert.trigger_condition === "SCHEDULE_ONLY" &&
    alert.mode === "AUTO" &&
    alert.strategy === "BUY_ONLY"
  );
}

/** "매월 25일 자동매수 중" 같은 한 줄 요약. isDcaAutoBuyPreset(alert)가 false면 빈 문자열을 반환한다. */
export function describeDcaAutoBuy(alert: RebalancingAlert | null | undefined): string {
  if (!isDcaAutoBuyPreset(alert) || !alert) return "";
  const day = alert.schedule_day_of_month ?? 1;
  return `매월 ${day}일 자동매수 중`;
}

/** 자동매수 실행 계좌의 예수금(원) — 백엔드 `jobs/dca_cash_shortfall.account_cash_krw`와 같은 규칙:
 * 포트폴리오에 해외 종목이 있을 때만 달러 예수금을 환산해 더한다(국내 종목만 사면 달러는 매수에 안 쓰임). */
export function dcaAccountCashKrw(
  account: { deposit_krw: number | null; deposit_usd?: number | null },
  itemMarkets: string[],
  usdRate: number | null,
): number {
  const krw = account.deposit_krw ?? 0;
  const usd = account.deposit_usd ?? 0;
  const hasOverseas = itemMarkets.some((m) => m !== "CASH" && isOverseasMarket(m));
  return hasOverseas && usd > 0 && usdRate ? krw + usd * usdRate : krw;
}

/** 월 적립액 대비 예수금 부족분(원). 부족하지 않거나 월 적립액 미설정이면 null.
 * (백엔드 사전 알림은 월 적립액 미설정 시 1만원 미만도 알리지만, 화면 경고는 비교 기준이 있을 때만 띄운다) */
export function dcaCashShortfallKrw(
  cashKrw: number,
  monthlyAmount: number | null | undefined,
): number | null {
  if (!monthlyAmount || monthlyAmount <= 0) return null;
  return cashKrw < monthlyAmount ? monthlyAmount - cashKrw : null;
}
