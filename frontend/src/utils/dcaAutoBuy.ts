import type { RebalancingAlert } from "@/api/alerts";
import type { PortfolioItem } from "@/api/portfolios";
import { isOverseasMarket } from "@/constants/markets";

/** 정액 적립 최소 금액(원) — 백엔드 `schemas/rebalancing/alert.DCA_AMOUNT_MIN_KRW`와 같은 값 */
export const DCA_AMOUNT_MIN_KRW = 10_000;

/** 해외 종목을 살 수 없는 절세 계좌 — 백엔드 `TAX_DEFERRED_TAX_TYPES`와 같은 집합 */
const TAX_DEFERRED = new Set(["ISA", "PENSION_SAVINGS", "IRP"]);

/** 리밸런싱 알림 설정이 "정기 적립식 자동매수" 형태(매월 특정일 · 무조건 실행 · 자동 · 매수만)와
 * 일치하는지 판정한다. threshold_pct는 사용자가 나중에 손으로 조정했을 수 있어 비교 대상에서
 * 제외한다 — 나머지 4개 필드가 이 조합이면 화면에는 "정기 적립식 자동매수"로 보여준다. */
export function isDcaAutoBuyPreset(
  alert:
    | (Pick<RebalancingAlert, "schedule_type" | "trigger_condition" | "mode" | "strategy"> &
        Partial<RebalancingAlert>)
    | null
    | undefined,
): boolean {
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
  const amount = alert.dca_amount_krw;
  return amount ? `매월 ${day}일 ${formatManwon(amount)} 자동매수 중` : `매월 ${day}일 자동매수 중`;
}

function formatManwon(krw: number): string {
  return krw % 10_000 === 0
    ? `${(krw / 10_000).toLocaleString()}만원`
    : `${krw.toLocaleString()}원`;
}

export interface DcaSplitRow {
  ticker: string;
  name: string;
  market: string;
  amountKrw: number;
  /** 해외 종목이면 현재 환율 기준 필요 달러(환율 모르면 null) */
  usd: number | null;
}

/** 정액 적립 금액을 목표 비중대로 나눈 미리보기 — 백엔드 `dca_allocation.dca_buy_rows`와 같은 대상 규칙:
 * 비중 0·현금 제외, 지수 그룹은 대표 종목(절세 계좌면 국내 대체), 절세 계좌의 해외 종목은 빼고 재정규화.
 * 실제 주수는 매수일 시세로 정해지므로 금액 기준 근사다. */
export function splitDcaAmount(
  items: PortfolioItem[],
  amountKrw: number,
  accountTaxType: string | null | undefined,
  usdRate: number | null,
): DcaSplitRow[] {
  const deferred = !!accountTaxType && TAX_DEFERRED.has(accountTaxType);
  const targets = items.flatMap((item) => {
    if (!(item.weight > 0) || item.market === "CASH") return [];
    let { ticker, name, market } = item;
    const alt = item.group?.domestic_alt;
    if (deferred && isOverseasMarket(market) && alt) {
      ({ ticker, name, market } = alt);
    }
    if (deferred && isOverseasMarket(market)) return [];
    return [{ ticker, name: name || ticker, market, weight: item.weight }];
  });
  const total = targets.reduce((sum, t) => sum + t.weight, 0);
  if (total <= 0 || amountKrw <= 0) return [];
  return targets.map((t) => {
    const amount = (amountKrw * t.weight) / total;
    return {
      ticker: t.ticker,
      name: t.name,
      market: t.market,
      amountKrw: Math.round(amount),
      usd:
        isOverseasMarket(t.market) && usdRate ? Math.round((amount / usdRate) * 100) / 100 : null,
    };
  });
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
 * 백엔드 `jobs/dca_cash_shortfall.is_cash_short`와 같은 비교 규칙 — 한쪽을 바꾸면 함께 맞출 것.
 * (백엔드 사전 알림은 월 적립액 미설정 시 1만원 미만도 알리지만, 화면 경고는 비교 기준이 있을 때만 띄운다) */
export function dcaCashShortfallKrw(
  cashKrw: number,
  monthlyAmount: number | null | undefined,
): number | null {
  if (!monthlyAmount || monthlyAmount <= 0) return null;
  return cashKrw < monthlyAmount ? monthlyAmount - cashKrw : null;
}

export interface DcaFixedShortfall {
  /** 국내 몫 대비 원화 예수금 부족분(원) — 충분하면 null */
  krwShort: number | null;
  /** 해외 몫 대비 달러 부족 — 충분하거나 환율을 모르면 null */
  usd: { required: number; available: number } | null;
}

/** 정액 적립(plans/120)의 사전 부족 판정 — 백엔드 `dca_cash_shortfall_service.fixed_amount_needs`와 같은 규칙:
 * 금액을 국내/해외 몫으로 나눠 원화 예수금과 **달러 예수금을 따로** 비교한다(해외는 환전한 달러로만 산다). */
export function dcaFixedAmountShortfall(
  account: { deposit_krw: number | null; deposit_usd?: number | null },
  items: PortfolioItem[],
  amountKrw: number,
  accountTaxType: string | null | undefined,
  usdRate: number | null,
): DcaFixedShortfall {
  const rows = splitDcaAmount(items, amountKrw, accountTaxType, usdRate);
  const krwNeeded = rows
    .filter((r) => !isOverseasMarket(r.market))
    .reduce((sum, r) => sum + r.amountKrw, 0);
  const usdNeeded = rows.reduce((sum, r) => sum + (r.usd ?? 0), 0);
  const cashKrw = account.deposit_krw ?? 0;
  const cashUsd = account.deposit_usd ?? 0;
  return {
    krwShort: krwNeeded > 0 && cashKrw < krwNeeded ? krwNeeded - cashKrw : null,
    usd:
      usdNeeded > 0 && cashUsd < usdNeeded
        ? { required: Math.round(usdNeeded * 100) / 100, available: cashUsd }
        : null,
  };
}
