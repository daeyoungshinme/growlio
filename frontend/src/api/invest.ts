import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "./client";

export interface DCAProjectionPoint {
  month: string;
  projected_krw: number;
  actual_krw: number | null;
  achievement_pct: number | null;
  has_data: boolean;
}

export interface YearlyAchievement {
  year: number;
  projected_year_end_krw: number;
  actual_year_end_krw: number | null;
  achievement_pct: number | null;
  has_data: boolean;
}

export interface GoalAccelerationScenario {
  years_earlier: number;
  new_expected_goal_date: string;
  required_monthly_deposit: number;
  required_annual_deposit: number;
  extra_monthly_deposit: number;
  required_return_pct: number | null;
  extra_return_pct: number | null;
}

export interface GoalTimeline {
  months_to_goal: number | null;
  expected_goal_date: string | null;
  actual_expected_goal_date: string | null;
  current_progress_pct: number | null;
  on_track: boolean | null;
  lead_lag_months: number | null;
  acceleration_scenarios: GoalAccelerationScenario[];
}

export interface DCASettings {
  monthly_deposit_amount: number | null;
  goal_annual_return_pct: number | null;
  goal_amount: number | null;
  goal_start_date: string | null;
  goal_initial_amount: number | null;
}

export interface DCAAnalysisData {
  settings: DCASettings;
  projection_months: DCAProjectionPoint[];
  yearly_achievements: YearlyAchievement[];
  goal_timeline: GoalTimeline;
  is_configured: boolean;
}

export const fetchDCAAnalysis = () => apiGet<DCAAnalysisData>("/invest/dca-analysis");

export interface MonthlyProjected {
  month: number;
  amount_krw: number;
}

export interface YearlyReceived {
  year: number;
  amount_krw: number;
}

export interface DividendPlanData {
  annual_dividend_goal: number | null;
  estimated_annual_krw: number;
  estimated_monthly_krw: number;
  actual_annual_received_krw: number;
  goal_achievement_pct: number | null;
  required_dividend_yield_pct: number | null;
  current_dividend_yield_pct: number | null;
  total_assets_krw: number;
  monthly_projected: MonthlyProjected[];
  monthly_received: { month: string; amount: number }[];
  yearly_received: YearlyReceived[];
}

export const fetchDividendPlan = () => apiGet<DividendPlanData>("/invest/dividend-plan");

export interface DepositGuideItem {
  annual_return_pct: number;
  required_monthly_deposit: number;
  required_annual_deposit: number;
}

export interface GoalFeasibilityPreview {
  required_return_pct: number | null;
  pv: number;
  n_months: number;
  note: string | null;
  deposit_guide: DepositGuideItem[];
}

export const fetchGoalFeasibility = (params: {
  goal_amount: number;
  target_year: number;
  monthly_deposit_amount?: number;
  initial_amount?: number;
}) => apiGet<GoalFeasibilityPreview>("/invest/goal-feasibility", { params });

// ── 달러 환전 계획(plans/96) — 예측이 아닌 1년 통계적 위치 + 해외 적립 필요 달러 분할 ──

export type FxZone = "CHEAP" | "NEUTRAL" | "EXPENSIVE";
export type FxPlanStatus =
  "OK" | "SUFFICIENT" | "NO_DEPOSIT_GOAL" | "NO_OVERSEAS" | "NO_PORTFOLIO" | "NO_RATE";

export interface FxPosition {
  rate: number;
  low_1y: number;
  high_1y: number;
  /** 1년 종가 중 현재보다 낮았던 비율(%) — 낮을수록 달러가 싸다 */
  percentile_1y: number;
  ma20: number;
  ma60: number;
  deviation_ma20_pct: number;
  deviation_ma60_pct: number;
  sigma_1m: number;
  range_1m_low: number;
  range_1m_high: number;
  zone: FxZone;
}

export interface FxTranche {
  label: string;
  /** null = 지금(또는 적립일) 환전 */
  target_rate: number | null;
  usd: number;
  krw_estimate: number;
}

/** SYNCED = 계좌관리의 마지막 동기화 값(plans/127), MANUAL = 수기 계좌에 직접 입력한 값 */
export type FxHeldUsdSource = "SYNCED" | "MANUAL";

export interface FxPlanHeldAccount {
  account_id: string;
  name: string;
  usd: number;
  source: FxHeldUsdSource;
  /** 브로커 계좌의 마지막 동기화 시각(수기는 null) */
  synced_at?: string | null;
  /** 추가 환전 항목(여행 등)이 이 계좌에 둔 달러 — usd는 이미 뺀 값. 옛 persist 캐시엔 없을 수 있다 */
  reserved_usd?: number;
}

export interface FxPlanData {
  position: FxPosition | null;
  /** false = 실시간 환율이 없어 1년 일봉 마지막 종가 기준 */
  rate_is_live: boolean;
  status: FxPlanStatus;
  portfolio_id: string | null;
  portfolio_name: string | null;
  portfolio_options: { id: string; name: string }[];
  months: number;
  overseas_weight_pct: number;
  monthly_deposit_krw: number | null;
  monthly_need_usd: number;
  held_usd: number;
  need_usd: number;
  tranches: FxTranche[];
  /** plans/121 B — 아래 셋은 옛 persist 캐시엔 없을 수 있다 */
  /** DCA_AMOUNT = 정액 적립 금액의 해외 몫, MONTHLY_GOAL = 월 적립액 × 해외 비중 */
  deposit_source?: "DCA_AMOUNT" | "MONTHLY_GOAL" | null;
  /** 보유 달러 기준 시각 — 달러가 있는 브로커 계좌 중 가장 오래된 동기화(plans/127) */
  held_usd_synced_at?: string | null;
  /** 보유 달러 계좌별 내역(0달러 제외, 큰 순) — 옛 persist 캐시엔 없을 수 있다 */
  held_usd_accounts?: FxPlanHeldAccount[];
  /** 환전 대기 중인 적립 매수를 진행하려면 지금 더 필요한 달러 */
  waiting_fx_usd?: number;
  /** 추가 환전 항목(여행 등)이 증권 계좌에 둔 달러 — held_usd에서 뺐다(plans/123 후속) */
  reserved_usd?: number;
}

export const fetchFxPlan = (months: number, portfolioId?: string | null) => {
  const params = new URLSearchParams({ months: String(months) });
  if (portfolioId) params.set("portfolio_id", portfolioId);
  return apiGet<FxPlanData>(`/invest/fx-plan?${params.toString()}`);
};

export interface FxPlanAlertSyncResult {
  created: number;
  updated: number;
  removed: number;
  /** 같은 목표의 직접 등록한 알림이 있어 만들지 않은 구간 수 */
  skipped_manual: number;
  /** 다른 포트폴리오 계획이 같은 목표 알림을 이미 가져 만들지 않은 구간 수 — 같은 환율 알림은 하나만 둔다 */
  skipped_shared: number;
}

/** 계획 구간 목표로 환율 알림을 맞춘다 — 새 목표는 만들고 빠진 미발동 계획 알림은 지운다(plans/121). */
export const syncFxPlanAlerts = (
  portfolioId: string,
  targets: { target_rate: number; usd: number }[],
) =>
  apiPut<FxPlanAlertSyncResult>("/invest/fx-plan/alerts", { portfolio_id: portfolioId, targets });

// ── 추가 환전 항목(여행 등, plans/123) — 적립 계획과 따로, 증권 계좌 달러로 상쇄하지 않는다 ──

/** OK = 구간 있음, DONE = 다 환전함, PAST_DUE = 필요일 지남, NO_RATE = 환율을 몰라 구간 계산 안 함 */
export type FxExtraNeedStatus = "OK" | "DONE" | "PAST_DUE" | "NO_RATE";

export interface FxExtraNeed {
  id: string;
  name: string;
  amount_usd: number;
  exchanged_usd: number;
  remaining_usd: number;
  /** YYYY-MM-DD */
  due_date: string;
  /** 음수면 필요일이 지남 */
  days_left: number;
  status: FxExtraNeedStatus;
  tranches: FxTranche[];
  /** 이 달러를 둔 증권 계좌 — 있으면 적립 환전 계획 보유 달러에서 exchanged_usd만큼 뺀다 */
  reserved_account_id?: string | null;
  reserved_account_name?: string | null;
}

export interface FxExtraNeedsData {
  /** 구간 계산에 쓴 환율(항목이 없거나 환율을 모르면 null) */
  rate: number | null;
  rate_is_live: boolean;
  needs: FxExtraNeed[];
}

export interface FxExtraNeedInput {
  name: string;
  amount_usd: number;
  exchanged_usd: number;
  due_date: string;
  /** null = 계좌 밖(은행·트래블카드) — 수정 때 null을 보내면 해제된다 */
  reserved_account_id: string | null;
}

export const fetchFxExtraNeeds = () => apiGet<FxExtraNeedsData>("/invest/fx-extra-needs");

export const createFxExtraNeed = (data: FxExtraNeedInput) =>
  apiPost<FxExtraNeed>("/invest/fx-extra-needs", data);

export const updateFxExtraNeed = (id: string, data: Partial<FxExtraNeedInput>) =>
  apiPatch<FxExtraNeed>(`/invest/fx-extra-needs/${id}`, data);

/** 항목을 지운다 — 이 항목으로 등록한 구간 알림도 서버에서 함께 지워진다 */
export const deleteFxExtraNeed = (id: string) => apiDelete(`/invest/fx-extra-needs/${id}`);

/** 추가 환전 항목의 구간 목표로 환율 알림을 맞춘다 — 적립 계획 알림은 건드리지 않는다 */
export const syncFxExtraNeedAlerts = (
  id: string,
  targets: { target_rate: number; usd: number }[],
) => apiPut<FxPlanAlertSyncResult>(`/invest/fx-extra-needs/${id}/alerts`, { targets });
