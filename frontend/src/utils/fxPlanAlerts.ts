import { isFxPlanAlert, type ExchangeRateAlert } from "@/api/alerts";
import type { FxTranche } from "@/api/invest";

/** 목표 환율 비교 키(센트 단위 정수) — 백엔드 `fx_plan_service._rate_key`와 같은 규칙 */
export const rateKey = (rate: number) => Math.round(Number(rate) * 100);

/**
 * 계획 금액이 이 비율(최소 1달러) 넘게 달라지면 알림을 다시 맞춰야 한다고 본다. 구간 금액은 실시간 환율·보유
 * 달러로 매번 다시 계산돼 몇 달러씩 흔들린다 — 절대 1달러면 5분 재조회마다 "바꾸기"로 돌아갔다(plans/122 C3)
 */
const PLANNED_USD_TOLERANCE_RATIO = 0.05;
const usdMatches = (registered: number, planned: number) =>
  Math.abs(registered - planned) <= Math.max(1, planned * PLANNED_USD_TOLERANCE_RATIO);

/** 계획 알림의 범위 — 포트폴리오 적립 계획 또는 추가 환전 항목(plans/123). 서버 `_in_scope`와 같은 규칙 */
export type FxPlanAlertScope = { portfolioId: string | null } | { fxNeedId: string };

const inScope = (a: ExchangeRateAlert, scope: FxPlanAlertScope) =>
  "fxNeedId" in scope
    ? a.fx_need_id === scope.fxNeedId
    : a.portfolio_id === scope.portfolioId && !a.fx_need_id;

/**
 * 계획 구간과 등록된 환율 알림 비교(plans/121).
 * - planRates: 이 범위에서 계획으로 만든 활성·미발동 알림의 목표
 * - manualRates: 계획 구간과 같은 목표의 직접 등록한 활성 BELOW 알림(서버가 건너뜀)
 * - inSync: 모든 구간이 (금액까지) 등록돼 있고 빠진 목표의 계획 알림이 없음
 * 알림을 불러오기 전엔 inSync=false — 버튼은 "확인 중"으로 잠긴다.
 */
export function planAlertState(
  alerts: ExchangeRateAlert[] | undefined,
  tranches: FxTranche[] | undefined,
  scope: FxPlanAlertScope,
) {
  const targets = (tranches ?? []).flatMap((t) =>
    t.target_rate === null ? [] : [{ target_rate: t.target_rate, usd: t.usd }],
  );
  const active = (alerts ?? []).filter((a) => a.is_active && a.direction === "BELOW");
  const planAlerts = active.filter(
    (a) => isFxPlanAlert(a) && inScope(a, scope) && a.triggered_at === null,
  );
  const targetKeys = new Set(targets.map((t) => rateKey(t.target_rate)));
  const manualRates = new Set(
    active
      .filter((a) => !isFxPlanAlert(a))
      .map((a) => rateKey(a.target_rate))
      .filter((k) => targetKeys.has(k)),
  );
  const planUsdByRate = new Map(planAlerts.map((a) => [rateKey(a.target_rate), a.planned_usd]));
  const inSync =
    alerts !== undefined &&
    planAlerts.every((a) => targetKeys.has(rateKey(a.target_rate))) &&
    targets.every((t) => {
      const key = rateKey(t.target_rate);
      if (manualRates.has(key)) return true;
      const usd = planUsdByRate.get(key);
      return usd != null && usdMatches(Number(usd), t.usd);
    });
  return {
    targets,
    planRates: new Set(planUsdByRate.keys()),
    manualRates,
    planAlertCount: planAlerts.length,
    inSync,
  };
}

export type PlanAlertState = ReturnType<typeof planAlertState>;

export function syncToastMessage(
  result: { created: number; updated: number; removed: number; skipped_manual: number },
  targetCount: number,
): string {
  if (targetCount === 0) {
    return result.removed > 0
      ? `환전 계획 알림 ${result.removed}건을 해제했습니다`
      : "해제할 환전 계획 알림이 없습니다";
  }
  const synced = result.created + result.updated;
  const parts =
    synced > 0
      ? [`목표 환율 알림 ${synced}건을 맞췄습니다`]
      : ["계획 목표에 직접 등록한 알림이 이미 있어 새로 만들지 않았습니다"];
  if (result.removed > 0) parts.push(`옛 목표 ${result.removed}건 해제`);
  if (result.skipped_manual > 0) parts.push(`직접 등록한 알림 ${result.skipped_manual}건은 그대로`);
  return parts.join(" · ");
}

/** 알림 버튼 문구 — 적립 계획·추가 환전 항목 공용 */
export function syncButtonLabel(
  plan: PlanAlertState,
  alertsLoaded: boolean,
  isPending: boolean,
): string {
  if (!alertsLoaded) return "알림 목록 확인 중";
  if (isPending) return "등록 중…";
  if (plan.inSync) return "목표 환율 알림 등록됨";
  if (plan.targets.length === 0) return `이 계획으로 등록한 알림 ${plan.planAlertCount}건 해제`;
  return plan.planAlertCount > 0 ? "알림을 새 계획으로 바꾸기" : "목표 환율 알림 등록";
}
