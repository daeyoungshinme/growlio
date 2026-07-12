import type { AccountTaxType, InvestmentHorizon } from "@/api/assets";

// 백엔드 backend/app/services/rebalancing_order_builder.py::recommend_drift_threshold_pct와 동기화 유지.
const HORIZON_THRESHOLD_ADJUSTMENT: Record<InvestmentHorizon, number> = {
  SHORT_TERM: -1.5,
  MID_TERM: 0,
  LONG_TERM: 1.5,
};

const TAX_TYPE_BASE_THRESHOLD_PCT: Record<AccountTaxType, number> = {
  GENERAL: 5.0,
  ISA: 7.0,
  PENSION_SAVINGS: 7.0,
  IRP: 7.0,
  OVERSEAS_DEDICATED: 6.5,
};

const MIN_RECOMMENDED_THRESHOLD_PCT = 1.0;
const MAX_RECOMMENDED_THRESHOLD_PCT = 20.0;

/**
 * 계좌 tax_type·investment_horizon 기반 PER_ACCOUNT 알림 임계값 추천치를 계산한다.
 * UI 초기값 제안일 뿐이며 사용자가 언제든 override 가능하다.
 */
export function recommendDriftThresholdPct(
  taxType: AccountTaxType | null | undefined,
  investmentHorizon: InvestmentHorizon | null | undefined,
): number {
  const base =
    TAX_TYPE_BASE_THRESHOLD_PCT[taxType ?? "GENERAL"] ?? TAX_TYPE_BASE_THRESHOLD_PCT.GENERAL;
  const adjustment = investmentHorizon ? (HORIZON_THRESHOLD_ADJUSTMENT[investmentHorizon] ?? 0) : 0;
  const clamped = Math.min(
    Math.max(base + adjustment, MIN_RECOMMENDED_THRESHOLD_PCT),
    MAX_RECOMMENDED_THRESHOLD_PCT,
  );
  return Math.round(clamped * 10) / 10;
}
