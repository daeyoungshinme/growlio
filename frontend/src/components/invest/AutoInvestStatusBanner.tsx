import { ArrowRight, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchPortfolios } from "@/api/portfolios";
import { fetchRebalancingAlerts } from "@/api/alerts";
import { fetchAccounts } from "@/api/assets";
import { fetchSettings } from "@/api/settings";
import { useExchangeRate } from "@/hooks/useExchangeRate";
import { fmtKrw } from "@/utils/format";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { mergeAlertsByPortfolio } from "@/utils/portfolio";
import {
  dcaAccountCashKrw,
  dcaCashShortfallKrw,
  describeDcaAutoBuy,
  isDcaAutoBuyPreset,
} from "@/utils/dcaAutoBuy";

/** "정기 적립식 자동매수"(리밸런싱 AUTO의 SCHEDULE_ONLY+BUY_ONLY 프리셋) 설정 여부를 한 줄로
 * 보여주고, /rebalancing 실행 화면으로 딥링크한다. 적립 계획 탭에서 이 기능의 존재를 알리는
 * 진입점 — 실제 설정 UI는 RebalancingAlertModal의 "빠른 설정"에 있다. */
export default function AutoInvestStatusBanner() {
  const { data: portfolios } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
    staleTime: STALE_TIME.MEDIUM,
  });
  const { data: alerts } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlerts,
    queryFn: fetchRebalancingAlerts,
    staleTime: STALE_TIME.MEDIUM,
  });

  const { data: accounts } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
    staleTime: STALE_TIME.MEDIUM,
  });
  const { data: settings } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });
  const usdRate = useExchangeRate();

  if (!portfolios || portfolios.length === 0) return null;

  const alertByPortfolioId = mergeAlertsByPortfolio(alerts ?? []);
  const activeEntry = portfolios
    .map((p) => ({ portfolio: p, alert: alertByPortfolioId[p.id] }))
    .find(({ alert }) => isDcaAutoBuyPreset(alert));

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
  const shortfallKrw =
    cashKrw != null ? dcaCashShortfallKrw(cashKrw, settings?.monthly_deposit_amount) : null;

  // 대상 포트폴리오가 하나로 정해지면(DCA 설정된 포트폴리오, 또는 포트폴리오가 1개뿐) openAlert=1로
  // 알림 설정 모달까지 바로 연다. 여러 개 중 고르는 경우만 목록으로 보낸다.
  const targetId = activeEntry?.portfolio.id ?? (portfolios.length === 1 ? portfolios[0].id : null);
  const linkTo = targetId
    ? `/rebalancing?rtab=포트폴리오&portfolioId=${targetId}&openAlert=1`
    : `/rebalancing?rtab=포트폴리오`;

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
        <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
          {activeEntry
            ? `정기 적립식 ${describeDcaAutoBuy(activeEntry.alert)}`
            : "정기 적립식 자동매수를 설정해보세요"}
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-500 truncate">
          {activeEntry
            ? activeEntry.portfolio.name
            : "매달 지정한 날짜에 목표 비중대로 자동 매수됩니다"}
        </p>
        {shortfallKrw != null && cashKrw != null && (
          <p className="text-xs font-medium text-amber-600 dark:text-amber-400 mt-0.5">
            예수금 {fmtKrw(cashKrw)} · 월 적립액보다 {fmtKrw(shortfallKrw)} 부족 — 예정일 전에
            입금하세요
          </p>
        )}
      </div>
      <Link
        to={linkTo}
        className="shrink-0 flex items-center gap-1 text-xs text-blue-500 dark:text-blue-400 hover:underline"
      >
        {activeEntry ? "설정 관리" : "설정하기"} <ArrowRight size={11} />
      </Link>
    </div>
  );
}
