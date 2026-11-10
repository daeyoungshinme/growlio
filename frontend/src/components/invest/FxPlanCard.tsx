import { useState } from "react";
import { Link } from "react-router-dom";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchFxPlan, syncFxPlanAlerts, type FxPlanData, type FxZone } from "@/api/invest";
import { isFxPlanAlert, type ExchangeRateAlert } from "@/api/alerts";
import { exchangeRateAlertsQuery } from "@/api/queryOptions";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { SELECT_SM } from "@/constants/inputStyles";
import { STALE_TIME } from "@/constants/queryConfig";
import { ALERT_TABS } from "@/constants/tabs";
import Tabs from "@/components/common/Tabs";
import SkeletonCard from "@/components/common/SkeletonCard";
import { fmtKrw, fmtPct, clampPct, fmtUsd } from "@/utils/format";
import { invalidateAlertData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { extractErrorMessage, getHttpStatus } from "@/utils/error";
import { notificationSettingsUrl } from "@/utils/tabUrl";
import { rebalancingUrl } from "@/utils/rebalancingUrl";

const MONTH_OPTIONS = ["1개월", "3개월", "6개월"] as const;
type MonthOption = (typeof MONTH_OPTIONS)[number];
const MONTHS: Record<MonthOption, number> = { "1개월": 1, "3개월": 3, "6개월": 6 };

const ZONE_LABEL: Record<FxZone, { text: string; className: string }> = {
  CHEAP: {
    text: "1년 중 낮은 편",
    className: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
  },
  NEUTRAL: {
    text: "1년 중 중간",
    className: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  },
  EXPENSIVE: {
    text: "1년 중 높은 편",
    className: "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
  },
};

const fmtRate = (n: number) => `${n.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}원`;
const fmtUsdWhole = (n: number) => fmtUsd(n, 0);

/** 목표 환율 비교 키(센트 단위 정수) — 백엔드 `fx_plan_service._rate_key`와 같은 규칙 */
const rateKey = (rate: number) => Math.round(Number(rate) * 100);
/**
 * 계획 금액이 이 비율(최소 1달러) 넘게 달라지면 알림을 다시 맞춰야 한다고 본다. 구간 금액은 실시간 환율·보유
 * 달러로 매번 다시 계산돼 몇 달러씩 흔들린다 — 절대 1달러면 5분 재조회마다 "바꾸기"로 돌아갔다(plans/122 C3)
 */
const PLANNED_USD_TOLERANCE_RATIO = 0.05;
const usdMatches = (registered: number, planned: number) =>
  Math.abs(registered - planned) <= Math.max(1, planned * PLANNED_USD_TOLERANCE_RATIO);

/**
 * 계획 구간과 등록된 환율 알림 비교(plans/121).
 * - planRates: 이 포트폴리오에서 계획으로 만든 활성·미발동 알림의 목표
 * - manualRates: 계획 구간과 같은 목표의 직접 등록한 활성 BELOW 알림(서버가 건너뜀)
 * - inSync: 모든 구간이 (금액까지) 등록돼 있고 빠진 목표의 계획 알림이 없음
 * 알림을 불러오기 전엔 inSync=false — 버튼은 "확인 중"으로 잠긴다.
 */
function planAlertState(alerts: ExchangeRateAlert[] | undefined, data: FxPlanData | undefined) {
  const targets = (data?.tranches ?? []).flatMap((t) =>
    t.target_rate === null ? [] : [{ target_rate: t.target_rate, usd: t.usd }],
  );
  const active = (alerts ?? []).filter((a) => a.is_active && a.direction === "BELOW");
  const planAlerts = active.filter(
    (a) => isFxPlanAlert(a) && a.portfolio_id === data?.portfolio_id && a.triggered_at === null,
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

function syncToastMessage(
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

interface Props {
  /** 월 적립액 미설정 시 "설정 편집" 열기 */
  onEditGoal?: () => void;
}

function PositionBlock({ position }: { position: NonNullable<FxPlanData["position"]> }) {
  const span = position.high_1y - position.low_1y;
  const markerPct = span > 0 ? clampPct(((position.rate - position.low_1y) / span) * 100) : 50;
  const zone = ZONE_LABEL[position.zone];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 tabular-nums">
          {fmtRate(position.rate)}
        </p>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${zone.className}`}>
          {zone.text} · 하위 {position.percentile_1y.toFixed(0)}%
        </span>
      </div>
      <div>
        <div
          className="relative h-2 rounded-full bg-linear-to-r from-emerald-200 via-gray-200 to-rose-200 dark:from-emerald-900 dark:via-gray-700 dark:to-rose-900"
          role="img"
          aria-label={`1년 범위 중 현재 위치 ${markerPct.toFixed(0)}%`}
        >
          <span
            className="absolute top-1/2 h-4 w-1 -translate-x-1/2 -translate-y-1/2 rounded-sm bg-gray-900 dark:bg-gray-100"
            style={{ left: `${markerPct}%` }}
          />
        </div>
        <div className="mt-1 flex justify-between text-xs text-gray-400 dark:text-gray-500 tabular-nums">
          <span>1년 최저 {fmtRate(position.low_1y)}</span>
          <span>최고 {fmtRate(position.high_1y)}</span>
        </div>
      </div>
      <dl className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-gray-50 dark:bg-gray-800/60 px-2 py-2">
          <dt className="text-xs text-gray-500 dark:text-gray-400">20일선 대비</dt>
          <dd className="text-sm font-semibold tabular-nums">
            {fmtPct(position.deviation_ma20_pct, 1)}
          </dd>
        </div>
        <div className="rounded-lg bg-gray-50 dark:bg-gray-800/60 px-2 py-2">
          <dt className="text-xs text-gray-500 dark:text-gray-400">60일선 대비</dt>
          <dd className="text-sm font-semibold tabular-nums">
            {fmtPct(position.deviation_ma60_pct, 1)}
          </dd>
        </div>
        <div className="rounded-lg bg-gray-50 dark:bg-gray-800/60 px-2 py-2">
          <dt className="text-xs text-gray-500 dark:text-gray-400">1개월 ±1σ</dt>
          <dd className="text-sm font-semibold tabular-nums">±{position.sigma_1m.toFixed(0)}원</dd>
        </div>
      </dl>
      <p className="text-xs text-gray-400 dark:text-gray-500">
        1개월 예상 범위 {fmtRate(position.range_1m_low)} ~ {fmtRate(position.range_1m_high)} — 과거
        1년 변동성으로 계산한 범위이며 환율 예측이 아닙니다.
      </p>
    </div>
  );
}

export default function FxPlanCard({ onEditGoal }: Props) {
  const qc = useQueryClient();
  const [monthOption, setMonthOption] = useState<MonthOption>("3개월");
  const [portfolioId, setPortfolioId] = useState<string | null>(null);
  const months = MONTHS[monthOption];

  const { data, isLoading, isError, error } = useQuery({
    queryKey: QUERY_KEYS.fxPlan(months, portfolioId),
    queryFn: () => fetchFxPlan(months, portfolioId),
    staleTime: STALE_TIME.FIVE_MINUTES,
    // 월 탭·포트폴리오를 바꿀 때 카드 전체가 스켈레톤으로 바뀌며 탭 포커스가 사라지지 않게 (plans/99 B1)
    placeholderData: keepPreviousData,
  });
  const { data: alerts } = useQuery(exchangeRateAlertsQuery);

  const plan = planAlertState(alerts, data);

  // 고른 포트폴리오가 삭제되면 404가 계속 남는다 — 자동 선택으로 되돌린다 (plans/97 B3).
  // 일시적인 5xx·네트워크 오류에는 사용자의 선택을 지우지 않는다 (plans/99 B1)
  if (isError && portfolioId && getHttpStatus(error) === 404) setPortfolioId(null);

  const syncMutation = useMutation({
    mutationFn: (targets: { target_rate: number; usd: number }[]) =>
      syncFxPlanAlerts(data?.portfolio_id ?? "", targets),
    onSuccess: (result, targets) => {
      void invalidateAlertData(qc);
      toast(syncToastMessage(result, targets.length), "success");
    },
    onError: (e) => {
      void invalidateAlertData(qc);
      toast(extractErrorMessage(e, "알림 등록에 실패했습니다"), "error");
    },
  });

  // 계획 구간이 없어진 상태(달러 충분·월 적립액 없음·해외 종목 없음)에도 옛 계획 알림은 남아 다시 발동한다 —
  // 어느 상태에서든 지울 수 있게 한다(plans/122 C2)
  const releaseButton = plan.planAlertCount > 0 && data?.portfolio_id && (
    <button
      onClick={() => syncMutation.mutate([])}
      disabled={syncMutation.isPending}
      className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} px-3 py-1.5 text-sm font-medium text-blue-600 dark:text-blue-400 disabled:opacity-50`}
    >
      이 계획으로 등록한 알림 {plan.planAlertCount}건 해제
    </button>
  );

  if (isLoading) return <SkeletonCard rows={4} height="h-5" />;
  if (isError || !data) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        환전 계획을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.
      </p>
    );
  }

  // 선택한 포트폴리오가 후보(해외 종목 보유)에서 빠졌어도 선택 상태를 보여 준다
  const pickerOptions =
    data.portfolio_id && !data.portfolio_options.some((o) => o.id === data.portfolio_id)
      ? [
          { id: data.portfolio_id, name: data.portfolio_name ?? "선택한 포트폴리오" },
          ...data.portfolio_options,
        ]
      : data.portfolio_options;
  const portfolioPicker = pickerOptions.length > 1 && (
    <select
      aria-label="포트폴리오 선택"
      className={SELECT_SM}
      value={data.portfolio_id ?? ""}
      onChange={(e) => setPortfolioId(e.target.value)}
    >
      {pickerOptions.map((o) => (
        <option key={o.id} value={o.id}>
          {o.name}
        </option>
      ))}
    </select>
  );

  return (
    <div className="space-y-5">
      {data.position ? (
        <>
          <PositionBlock position={data.position} />
          {!data.rate_is_live && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              실시간 환율을 불러오지 못해 최근 종가 기준으로 계산했습니다.
            </p>
          )}
        </>
      ) : (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          환율 1년 시세를 불러오지 못해 위치 판단 없이 계획만 보여드립니다.
        </p>
      )}

      {/* 고른 포트폴리오가 NO_OVERSEAS가 돼도 다른 후보로 옮길 수 있게 상태와 무관하게 보인다 (plans/99 B1) */}
      {data.status !== "OK" && data.status !== "SUFFICIENT" && portfolioPicker}

      {data.status === "NO_PORTFOLIO" ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          해외 종목이 들어 있는 포트폴리오가 없어 환전 계획을 세우지 않았습니다.
        </p>
      ) : data.status === "NO_OVERSEAS" ? (
        <div className="space-y-2">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {data.portfolio_options.length > 0
              ? "선택한 포트폴리오에 해외 종목이 없습니다. 다른 포트폴리오를 골라 주세요."
              : "해외 종목이 들어 있는 포트폴리오가 없어 환전 계획을 세우지 않았습니다."}
          </p>
          {releaseButton}
        </div>
      ) : data.status === "NO_RATE" ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          환율을 불러오지 못해 필요한 달러를 계산하지 않았습니다. 잠시 후 다시 시도해 주세요.
        </p>
      ) : data.status === "NO_DEPOSIT_GOAL" ? (
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-gray-500 dark:text-gray-400">
          <span>월 적립액을 설정하면 필요한 달러를 계산해 드립니다.</span>
          {onEditGoal && (
            <button
              onClick={onEditGoal}
              className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} px-3 py-1.5 text-sm font-medium text-blue-600 dark:text-blue-400`}
            >
              월 적립액 설정
            </button>
          )}
          {releaseButton}
        </div>
      ) : (
        <div className="space-y-4 border-t border-gray-100 dark:border-gray-800 pt-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <Tabs
              tabs={MONTH_OPTIONS}
              activeTab={monthOption}
              onChange={setMonthOption}
              variant="pill"
              fullWidth
            />
            {portfolioPicker}
          </div>

          <p className="text-sm text-gray-600 dark:text-gray-300">
            {data.deposit_source === "DCA_AMOUNT" ? (
              <>
                {data.portfolio_name} 정액 적립 월 {fmtKrw(data.monthly_deposit_krw ?? 0)}의 해외 몫
              </>
            ) : (
              <>
                {data.portfolio_name} 해외 비중 {data.overseas_weight_pct.toFixed(0)}% × 월{" "}
                {fmtKrw(data.monthly_deposit_krw ?? 0)}
              </>
            )}{" "}
            → 월 {fmtUsdWhole(data.monthly_need_usd)} × {data.months}개월 − 보유{" "}
            {fmtUsdWhole(data.held_usd)}
            {data.held_usd_is_live ? "(실시간)" : "(동기화 기준)"} ={" "}
            <span className="font-semibold text-gray-900 dark:text-gray-100">
              {fmtUsdWhole(data.need_usd)} 필요
            </span>
          </p>

          {(data.waiting_fx_usd ?? 0) > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-amber-50 px-3 py-2.5 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
              <span>
                환전을 기다리는 적립 매수가 있습니다. {fmtUsdWhole(data.waiting_fx_usd ?? 0)}를 지금
                환전하면 매수가 이어집니다.
              </span>
              <Link
                to={rebalancingUrl({ tab: "이력" })}
                className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} font-medium text-amber-900 underline dark:text-amber-200`}
              >
                대기 중인 매수 보기
              </Link>
            </div>
          )}

          {data.status === "SUFFICIENT" ? (
            <div className="space-y-2">
              <p className="text-sm text-emerald-700 dark:text-emerald-300">
                이미 보유한 달러로 {data.months}개월치 해외 적립이 가능합니다.
              </p>
              {releaseButton}
            </div>
          ) : (
            <>
              <ul className="divide-y divide-gray-100 dark:divide-gray-800 rounded-lg border border-gray-100 dark:border-gray-800">
                {data.tranches.map((t) => (
                  <li
                    key={t.target_rate ?? t.label}
                    className="flex items-center justify-between gap-3 px-3 py-2.5"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {t.label}
                      </p>
                      {t.target_rate !== null && plan.planRates.has(rateKey(t.target_rate)) && (
                        <p className="text-xs text-emerald-600 dark:text-emerald-400">
                          알림 등록됨
                        </p>
                      )}
                      {t.target_rate !== null && plan.manualRates.has(rateKey(t.target_rate)) && (
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          직접 등록한 알림 있음
                        </p>
                      )}
                    </div>
                    <div className="text-right tabular-nums">
                      <p className="text-sm font-semibold">{fmtUsdWhole(t.usd)}</p>
                      <p className="text-xs text-gray-400 dark:text-gray-500">
                        약 {fmtKrw(t.krw_estimate)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-gray-400 dark:text-gray-500">
                {data.months}개월 안에 목표 환율에 닿지 않으면 남은 금액은 적립일에 환전하세요.
                환전은 증권사 앱에서 직접 진행합니다.
              </p>
              {/* 목표 구간이 없어도(1년 시세 실패·환전 대기가 전액 등) 옛 계획 알림은 지울 수 있어야 한다(plans/122 C2) */}
              {(plan.targets.length > 0 || plan.planAlertCount > 0) && (
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <button
                    onClick={() => syncMutation.mutate(plan.targets)}
                    disabled={!alerts || plan.inSync || syncMutation.isPending}
                    className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} w-full sm:w-auto px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors`}
                  >
                    {!alerts
                      ? "알림 목록 확인 중"
                      : syncMutation.isPending
                        ? "등록 중…"
                        : plan.inSync
                          ? "목표 환율 알림 등록됨"
                          : plan.targets.length === 0
                            ? `이 계획으로 등록한 알림 ${plan.planAlertCount}건 해제`
                            : plan.planAlertCount > 0
                              ? "알림을 새 계획으로 바꾸기"
                              : "목표 환율 알림 등록"}
                  </button>
                  {/* 등록한 알림의 수정·삭제는 설정 › 알림 설정 › 환율 알림에서 (계획 106 C2) */}
                  {(plan.planAlertCount > 0 || plan.manualRates.size > 0) && (
                    <Link
                      to={notificationSettingsUrl(ALERT_TABS[0])}
                      className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} gap-1 text-sm text-blue-600 dark:text-blue-400 hover:underline`}
                    >
                      환율 알림 관리 →
                    </Link>
                  )}
                </div>
              )}
              {plan.planAlertCount > 0 && !plan.inSync && (
                <p className="text-xs text-gray-400 dark:text-gray-500">
                  환율·기간이 바뀌어 등록한 알림과 지금 계획의 목표가 다릅니다. 바꾸면 이 계획에서
                  만든 미발동 알림이 새 목표로 교체됩니다.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
