import { ArrowRight, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useExchangeRate } from "@/hooks/useExchangeRate";
import { fmtKrw, fmtUsdPrice } from "@/utils/format";
import { activeAlertsOnly, mergeAlertsByPortfolio } from "@/utils/portfolio";
import {
  dcaAccountCashKrw,
  dcaCashShortfallKrw,
  dcaFixedAmountShortfall,
  describeDcaAutoBuy,
  isDcaAutoBuyPreset,
} from "@/utils/dcaAutoBuy";
import { fetchRecentPlanLegs } from "@/api/rebalancingPlan";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { rebalancingUrl } from "@/utils/rebalancingUrl";
import {
  accountsQuery,
  portfoliosQuery,
  rebalancingAlertsQuery,
  settingsQuery,
} from "@/api/queryOptions";
import EmptyState from "@/components/common/EmptyState";

/** "정기 적립식 자동매수"(리밸런싱 AUTO의 SCHEDULE_ONLY+BUY_ONLY 프리셋) 설정 여부를 한 줄로
 * 보여주고, /rebalancing 실행 화면으로 딥링크한다. 적립 계획 탭에서 이 기능의 존재를 알리는
 * 진입점 — 실제 설정 UI는 RebalancingAlertModal의 "빠른 설정"에 있다. */
export default function AutoInvestStatusBanner() {
  const { data: portfolios } = useQuery(portfoliosQuery);
  const {
    data: alerts,
    isError: alertsFailed,
    refetch: refetchAlerts,
  } = useQuery(rebalancingAlertsQuery);

  const { data: accounts } = useQuery(accountsQuery);
  const { data: settings } = useQuery(settingsQuery);
  const usdRate = useExchangeRate();
  // 이력 탭과 같은 키 — 환전 대기(WAITING_FX) 해외 매수가 있으면 여기서도 알린다(plans/120)
  const { data: planLegs } = useQuery({
    queryKey: QUERY_KEYS.rebalancingPlans,
    queryFn: () => fetchRecentPlanLegs(30),
    staleTime: STALE_TIME.VERY_SHORT,
  });
  const fxWaitingCount = planLegs?.filter((leg) => leg.status === "WAITING_FX").length ?? 0;

  if (!portfolios || portfolios.length === 0) return null;

  // 조회 실패를 "자동매수 없음"으로 보이면 켜 둔 사용자가 "설정해보세요"를 보고 부족 경고도 놓친다
  if (alertsFailed && !alerts) {
    return (
      <EmptyState
        title="자동매수 상태를 불러오지 못했습니다."
        action={{ label: "다시 시도", onClick: () => void refetchAlerts() }}
        compact
      />
    );
  }

  // 꺼진 정기 적립식은 "자동매수 중"으로 보이면 안 된다(plans/63 P1-4)
  const alertByPortfolioId = activeAlertsOnly(mergeAlertsByPortfolio(alerts ?? []));
  const activeEntry = portfolios
    .map((p) => ({ portfolio: p, alert: alertByPortfolioId[p.id] }))
    .find(
      (e): e is { portfolio: (typeof portfolios)[number]; alert: NonNullable<typeof e.alert> } =>
        isDcaAutoBuyPreset(e.alert),
    );

  // 실행 계좌 예수금이 월 적립액보다 적으면 경고 — 자동매수는 계좌에 있는 예수금으로만 산다(계획 37 E5).
  // 실행 1~3일 전엔 백엔드가 이메일·푸시로도 알린다(jobs/dca_cash_shortfall.py).
  const execAccount = activeEntry?.alert.account_id
    ? accounts?.find((a) => a.id === activeEntry.alert.account_id)
    : undefined;
  const cashKrw =
    activeEntry && execAccount
      ? dcaAccountCashKrw(
          execAccount,
          activeEntry.portfolio.items.map((i) => i.market),
          usdRate,
        )
      : null;
  const fixedAmount = activeEntry?.alert.dca_amount_krw ?? null;
  // 정액이면 알림 금액 기준으로 원화·달러를 따로 본다 — 월 적립액 합산 비교는 정액이 없을 때만
  const fixed =
    activeEntry && execAccount && fixedAmount
      ? dcaFixedAmountShortfall(
          execAccount,
          activeEntry.portfolio.items,
          fixedAmount,
          execAccount.tax_type,
          usdRate,
        )
      : null;
  const shortfallKrw = fixed
    ? fixed.krwShort
    : cashKrw != null
      ? dcaCashShortfallKrw(cashKrw, settings?.monthly_deposit_amount)
      : null;

  // 대상 포트폴리오가 하나로 정해지면(DCA 설정된 포트폴리오, 또는 포트폴리오가 1개뿐) 알림 설정 모달까지
  // 바로 연다 — 미설정이면 `openAlert=dca`로 정기 적립식 프리셋 화면에 직행(M6), 설정돼 있으면 편집 화면.
  // 여러 개 중 고르는 경우만 목록으로 보낸다.
  const targetId =
    activeEntry?.portfolio.id ?? (portfolios.length === 1 ? (portfolios[0]?.id ?? null) : null);
  const linkTo = targetId
    ? rebalancingUrl({
        tab: "포트폴리오",
        portfolioId: targetId,
        openAlert: activeEntry ? "1" : "dca",
      })
    : rebalancingUrl({ tab: "포트폴리오" });

  return (
    <div className="card flex items-center gap-3">
      <div
        className={`shrink-0 p-2 rounded-full ${
          activeEntry
            ? "bg-green-100 dark:bg-green-950 text-green-600 dark:text-green-400"
            : "bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500"
        }`}
      >
        <RefreshCw size={16} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-800 dark:text-gray-200 break-keep">
          {activeEntry
            ? `정기 적립식 ${describeDcaAutoBuy(activeEntry.alert)}`
            : "정기 적립식 자동매수를 설정해보세요"}
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400 break-keep">
          {activeEntry
            ? activeEntry.portfolio.name
            : "매달 지정한 날짜에 목표 비중대로 자동 매수됩니다"}
        </p>
        {shortfallKrw != null && cashKrw != null && (
          <p className="text-xs font-medium text-amber-600 dark:text-amber-400 mt-0.5">
            {fixed
              ? `원화 예수금이 국내 몫보다 ${fmtKrw(shortfallKrw)} 부족 — 예정일 전에 입금하세요`
              : `예수금 ${fmtKrw(cashKrw)} · 월 적립액보다 ${fmtKrw(shortfallKrw)} 부족 — 예정일 전에 입금하세요`}
          </p>
        )}
        {fixed?.usd && (
          <p className="text-xs font-medium text-amber-600 dark:text-amber-400 mt-0.5">
            해외 몫 {fmtUsdPrice(fixed.usd.required)} 필요 · 보유 {fmtUsdPrice(fixed.usd.available)}{" "}
            — 예정일 전에 환전하세요
          </p>
        )}
        {fxWaitingCount > 0 && (
          <Link
            to={rebalancingUrl({ tab: "이력" })}
            className="block text-xs font-medium text-amber-700 dark:text-amber-300 mt-0.5 hover:underline"
          >
            달러 부족으로 기다리는 해외 매수가 있어요 — 환전 후 다시 매수 →
          </Link>
        )}
      </div>
      <Link
        to={linkTo}
        className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} shrink-0 flex items-center gap-1 text-xs text-blue-500 dark:text-blue-400 hover:underline`}
      >
        {activeEntry ? "설정 관리" : "자동매수 설정"} <ArrowRight size={11} />
      </Link>
    </div>
  );
}
