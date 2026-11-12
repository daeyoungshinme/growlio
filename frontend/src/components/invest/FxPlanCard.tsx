import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { syncFxPlanAlerts, type FxHeldUsdSource, type FxPlanData, type FxZone } from "@/api/invest";
import { accountsQuery, exchangeRateAlertsQuery, fxPlanQuery } from "@/api/queryOptions";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { SELECT_SM } from "@/constants/inputStyles";
import { ALERT_TABS } from "@/constants/tabs";
import Tabs from "@/components/common/Tabs";
import SkeletonCard from "@/components/common/SkeletonCard";
import { fmtKrw, fmtPct, clampPct, fmtUsd, relativeTime } from "@/utils/format";
import { isStockAccount, isSyncableAccount } from "@/utils/accounts";
import { useSyncAccounts } from "@/hooks/useSyncAccounts";
import { planAlertState, syncButtonLabel, syncToastMessage } from "@/utils/fxPlanAlerts";
import FxTrancheList from "@/components/invest/FxTrancheList";
import FxExtraNeedsSection from "@/components/invest/FxExtraNeedsSection";
import { invalidateAlertData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { extractErrorMessage, getHttpStatus } from "@/utils/error";
import { notificationSettingsUrl } from "@/utils/tabUrl";
import { rebalancingUrl } from "@/utils/rebalancingUrl";

// 기본 "3개월"은 `FX_PLAN_DEFAULT_MONTHS`(페이지 프리페치 키)와 같아야 한다
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

const HELD_SOURCE_LABEL: Record<FxHeldUsdSource, string> = {
  SYNCED: "동기화 기준",
  MANUAL: "직접 입력",
};

/** 산식의 보유 달러 괄호 라벨 — 계좌관리 동기화 값이라 언제 기준인지 보여 준다(plans/127) */
function heldUsdLabel(data: FxPlanData) {
  const syncedAt = data.held_usd_synced_at ? ` · ${relativeTime(data.held_usd_synced_at)}` : "";
  if ((data.held_usd_accounts ?? []).some((a) => a.source === "MANUAL"))
    return `(직접 입력 포함${syncedAt})`;
  return `(동기화 기준${syncedAt})`;
}

/**
 * 보유 달러는 계좌관리의 동기화 값이다 — 증권사 앱에서 환전한 직후엔 옛 값이라 증권 계좌를 동기화해 새로 받는다.
 * 0달러 계좌는 계획 응답의 계좌 내역에 없으므로 계좌 목록에서 고른다. 동기화 무효화가 계획도 다시 받는다.
 */
function RefreshHeldUsdButton() {
  const { data: accounts } = useQuery(accountsQuery);
  const { state, run } = useSyncAccounts();
  const ids = (accounts ?? [])
    .filter((a) => isStockAccount(a.asset_type) && isSyncableAccount(a.data_source))
    .map((a) => a.id);
  if (ids.length === 0) return null;
  const syncing = state === "syncing";
  return (
    <div className="flex flex-wrap items-center gap-x-2 text-xs text-gray-500 dark:text-gray-400">
      <span>증권사 앱에서 환전했다면 새로 받아 주세요.</span>
      <button
        onClick={() => {
          void run(ids).then((ok) => {
            if (!ok) toast("일부 계좌의 달러 예수금을 받지 못했습니다", "error");
          });
        }}
        disabled={syncing}
        className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} font-medium text-blue-600 dark:text-blue-400 disabled:opacity-50`}
      >
        {syncing ? "받는 중…" : "달러 예수금 새로 받기"}
      </button>
    </div>
  );
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

/**
 * 추가 환전 섹션은 환전 계획 응답(증권사 실시간 달러 조회로 느릴 수 있음)을 기다리지 않고 함께 조회한다 —
 * 계획 본문 안에 두면 본문 로딩이 끝난 뒤에야 마운트돼 요청이 직렬로 쌓인다(plans/124 D)
 */
export default function FxPlanCard({ onEditGoal }: Props) {
  return (
    <div className="space-y-5">
      <FxPlanBody onEditGoal={onEditGoal} />
      <FxExtraNeedsSection />
    </div>
  );
}

function FxPlanBody({ onEditGoal }: Props) {
  const qc = useQueryClient();
  const [monthOption, setMonthOption] = useState<MonthOption>("3개월");
  const [portfolioId, setPortfolioId] = useState<string | null>(null);
  const months = MONTHS[monthOption];

  const { data, isLoading, isError, error, isPlaceholderData } = useQuery({
    ...fxPlanQuery(months, portfolioId),
    // 월 탭·포트폴리오를 바꿀 때 카드 전체가 스켈레톤으로 바뀌며 탭 포커스가 사라지지 않게 (plans/99 B1)
    placeholderData: keepPreviousData,
  });

  // 기간 탭은 계획이 나온 상태(OK·SUFFICIENT)에서만 보인다 — 그때 나머지 기간을 미리 받아 탭 전환을 즉시로.
  // 서버는 증권사를 부르지 않는다(동기화 값, plans/127)
  const prefetchOtherMonths =
    !!data && !isPlaceholderData && (data.status === "OK" || data.status === "SUFFICIENT");
  useEffect(() => {
    if (!prefetchOtherMonths) return;
    for (const option of MONTH_OPTIONS) {
      if (MONTHS[option] !== months)
        void qc.prefetchQuery(fxPlanQuery(MONTHS[option], portfolioId));
    }
  }, [prefetchOtherMonths, months, portfolioId, qc]);
  const { data: alerts } = useQuery(exchangeRateAlertsQuery);

  const plan = planAlertState(alerts, data?.tranches, { portfolioId: data?.portfolio_id ?? null });

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
  // 기간·포트폴리오를 바꾸는 동안 data는 이전 계획(keepPreviousData) — 그 구간·포트폴리오로 알림을 맞추지 않게
  // 새 계획이 올 때까지 등록·해제 버튼을 막는다(plans/126 A3)
  const releaseButton = plan.planAlertCount > 0 && data?.portfolio_id && (
    <button
      onClick={() => syncMutation.mutate([])}
      disabled={syncMutation.isPending || isPlaceholderData}
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
            {heldUsdLabel(data)}
            {(data.reserved_usd ?? 0) > 0 && (
              <> (추가 환전 {fmtUsdWhole(data.reserved_usd ?? 0)} 제외)</>
            )}{" "}
            ={" "}
            <span className="font-semibold text-gray-900 dark:text-gray-100">
              {fmtUsdWhole(data.need_usd)} 필요
            </span>
          </p>

          {(data.held_usd_accounts?.length ?? 0) > 0 && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              보유 달러:{" "}
              {data.held_usd_accounts
                ?.map(
                  (a) =>
                    `${a.name} ${fmtUsdWhole(a.usd)}(${HELD_SOURCE_LABEL[a.source]}${
                      (a.reserved_usd ?? 0) > 0
                        ? `, 추가 환전 ${fmtUsdWhole(a.reserved_usd ?? 0)} 제외`
                        : ""
                    })`,
                )
                .join(" · ")}
            </p>
          )}

          <RefreshHeldUsdButton />

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
              <FxTrancheList
                tranches={data.tranches}
                planRates={plan.planRates}
                manualRates={plan.manualRates}
                sharedRates={plan.sharedRates}
              />
              <p className="text-xs text-gray-400 dark:text-gray-500">
                {data.months}개월 안에 목표 환율에 닿지 않으면 남은 금액은 적립일에 환전하세요.
                환전은 증권사 앱에서 직접 진행합니다.
              </p>
              {/* 목표 구간이 없어도(1년 시세 실패·환전 대기가 전액 등) 옛 계획 알림은 지울 수 있어야 한다(plans/122 C2) */}
              {(plan.targets.length > 0 || plan.planAlertCount > 0) && (
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <button
                    onClick={() => syncMutation.mutate(plan.targets)}
                    disabled={!alerts || plan.inSync || syncMutation.isPending || isPlaceholderData}
                    className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} w-full sm:w-auto px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors`}
                  >
                    {syncButtonLabel(plan, !!alerts, syncMutation.isPending)}
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
