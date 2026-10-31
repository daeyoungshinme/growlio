import { useState, type ReactNode } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchFxPlan, type FxPlanData, type FxZone } from "@/api/invest";
import { createExchangeRateAlert } from "@/api/alerts";
import { exchangeRateAlertsQuery } from "@/api/queryOptions";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { SELECT_SM } from "@/constants/inputStyles";
import { STALE_TIME } from "@/constants/queryConfig";
import Tabs from "@/components/common/Tabs";
import SkeletonCard from "@/components/common/SkeletonCard";
import { fmtKrw, fmtPct, clampPct, fmtUsd } from "@/utils/format";
import { invalidateAlertData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { extractErrorMessage, getHttpStatus } from "@/utils/error";

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

interface Props {
  /** 접힘 카드 안에 임베드될 때 — 외곽 card 스타일 생략 */
  flat?: boolean;
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
          className="relative h-2 rounded-full bg-gradient-to-r from-emerald-200 via-gray-200 to-rose-200 dark:from-emerald-900 dark:via-gray-700 dark:to-rose-900"
          role="img"
          aria-label={`1년 범위 중 현재 위치 ${markerPct.toFixed(0)}%`}
        >
          <span
            className="absolute top-1/2 h-4 w-1 -translate-x-1/2 -translate-y-1/2 rounded bg-gray-900 dark:bg-gray-100"
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

export default function FxPlanCard({ flat, onEditGoal }: Props) {
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

  const registered = new Set(
    (alerts ?? [])
      .filter((a) => a.is_active && a.direction === "BELOW")
      .map((a) => Number(a.target_rate)),
  );
  const targets = (data?.tranches ?? [])
    .map((t) => t.target_rate)
    .filter((r): r is number => r !== null);
  const pendingTargets = targets.filter((r) => !registered.has(r));

  // 고른 포트폴리오가 삭제되면 404가 계속 남는다 — 자동 선택으로 되돌린다 (plans/97 B3).
  // 일시적인 5xx·네트워크 오류에는 사용자의 선택을 지우지 않는다 (plans/99 B1)
  if (isError && portfolioId && getHttpStatus(error) === 404) setPortfolioId(null);

  const registerMutation = useMutation({
    mutationFn: async () => {
      for (const rate of pendingTargets) await createExchangeRateAlert(rate, "BELOW", 1);
    },
    onSuccess: () => {
      void invalidateAlertData(qc);
      toast(`목표 환율 알림 ${pendingTargets.length}건을 등록했습니다`, "success");
    },
    onError: (e) => {
      void invalidateAlertData(qc);
      toast(extractErrorMessage(e, "알림 등록에 실패했습니다"), "error");
    },
  });

  const wrap = (children: ReactNode) =>
    flat ? (
      <div className="space-y-5">{children}</div>
    ) : (
      <div className="card space-y-5">{children}</div>
    );

  if (isLoading) return <SkeletonCard rows={4} height="h-5" />;
  if (isError || !data) {
    return wrap(
      <p className="text-sm text-gray-500 dark:text-gray-400">
        환전 계획을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.
      </p>,
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

  return wrap(
    <>
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
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {data.portfolio_options.length > 0
            ? "선택한 포트폴리오에 해외 종목이 없습니다. 다른 포트폴리오를 골라 주세요."
            : "해외 종목이 들어 있는 포트폴리오가 없어 환전 계획을 세우지 않았습니다."}
        </p>
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
            {data.portfolio_name} 해외 비중 {data.overseas_weight_pct.toFixed(0)}% × 월{" "}
            {fmtKrw(data.monthly_deposit_krw ?? 0)} → 월 {fmtUsdWhole(data.monthly_need_usd)} ×{" "}
            {data.months}개월 − 보유 {fmtUsdWhole(data.held_usd)} ={" "}
            <span className="font-semibold text-gray-900 dark:text-gray-100">
              {fmtUsdWhole(data.need_usd)} 필요
            </span>
          </p>

          {data.status === "SUFFICIENT" ? (
            <p className="text-sm text-emerald-700 dark:text-emerald-300">
              이미 보유한 달러로 {data.months}개월치 해외 적립이 가능합니다.
            </p>
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
                      {t.target_rate !== null && registered.has(t.target_rate) && (
                        <p className="text-xs text-emerald-600 dark:text-emerald-400">
                          알림 등록됨
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
              {targets.length > 0 && (
                <button
                  onClick={() => registerMutation.mutate()}
                  disabled={pendingTargets.length === 0 || registerMutation.isPending}
                  className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} w-full sm:w-auto px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors`}
                >
                  {pendingTargets.length === 0
                    ? "목표 환율 알림 등록됨"
                    : registerMutation.isPending
                      ? "등록 중…"
                      : "목표 환율 알림 등록"}
                </button>
              )}
            </>
          )}
        </div>
      )}
    </>,
  );
}
