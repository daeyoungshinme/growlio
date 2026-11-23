import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { completeDipBuy, type DipBuyPlan, type DipBuyTierState } from "@/api/dipBuy";
import { dipBuyQuery, portfoliosQuery, rebalancingAlertsQuery } from "@/api/queryOptions";
import EmptyState from "@/components/common/EmptyState";
import SkeletonCard from "@/components/common/SkeletonCard";
import ConfirmModal from "@/components/common/ConfirmModal";
import DipBuySettingsModal from "@/components/invest/DipBuySettingsModal";
import { FORM_LABEL, INPUT_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_MIN, TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { isOverseasMarket } from "@/constants/markets";
import { activeAlertsOnly, mergeAlertsByPortfolio } from "@/utils/portfolio";
import { isDcaAutoBuyPreset } from "@/utils/dcaAutoBuy";
import { invalidateDipBuyData } from "@/utils/queryInvalidation";
import { rebalancingUrl } from "@/utils/rebalancingUrl";
import { fmtKrw, fmtKrwPreview, fmtUsdPrice, parseYmd } from "@/utils/format";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

const STATE_LABEL: Record<DipBuyTierState, { text: string; className: string }> = {
  DONE: {
    text: "추매 완료",
    className: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
  },
  DUE: {
    text: "이번 적립일",
    className: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
  },
  WAITING: {
    text: "대기",
    className: "bg-gray-50 text-gray-500 dark:bg-gray-900 dark:text-gray-400",
  },
};

const WEEKDAYS = "일월화수목금토";

function runDateLabel(ymd: string): string {
  const { year, month, day } = parseYmd(ymd);
  const weekday = WEEKDAYS[new Date(year, month - 1, day).getDay()] ?? "";
  return `${month}월 ${day}일(${weekday})`;
}

const fmtDrawdown = (pct: number | null) => (pct == null ? "확인 불가" : `${pct.toFixed(1)}%`);

/** 계획 › 적립 계획 "낙폭 추매 안내"(plans/147) — 적립은 그대로, 여윳돈을 지수 낙폭 구간별로 나눠 안내. 주문 없음 */
export default function DipBuyCard() {
  const { data, isLoading, isError, refetch } = useQuery(dipBuyQuery);
  const { data: portfolios } = useQuery(portfoliosQuery);
  const { data: alerts } = useQuery(rebalancingAlertsQuery);
  const [editing, setEditing] = useState<DipBuyPlan | "new" | null>(null);

  if (isLoading) return <SkeletonCard rows={4} height="h-5" />;
  if (isError && !data) {
    return (
      <EmptyState
        title="추매 안내를 불러오지 못했습니다."
        action={{ label: "다시 시도", onClick: () => void refetch() }}
        compact
      />
    );
  }

  const plans = data?.plans ?? [];
  const usedIds = new Set(plans.map((p) => p.portfolio_id));
  const portfolioOptions = (portfolios ?? [])
    .filter((p) => !usedIds.has(p.id))
    .map((p) => ({ id: p.id, name: p.name }));
  // 새 설정의 기본 포트폴리오는 정기 적립식 자동매수를 켠 포트폴리오
  const alertByPortfolio = activeAlertsOnly(mergeAlertsByPortfolio(alerts ?? []));
  const defaultPortfolioId =
    portfolioOptions.find((p) => isDcaAutoBuyPreset(alertByPortfolio[p.id]))?.id ?? null;
  const resetPct = data?.reset_drawdown_pct ?? 3;

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500 dark:text-gray-400 break-keep">
        매달 적립은 그대로 두고, 따로 모아 둔 여윳돈을 지수가 52주 고점 대비 내려간 구간마다 나눠
        사도록 알려드려요. 적립금을 줄여 모은 돈이 아니라 원래 투자하지 않던 여윳돈일 때 쓰세요.
        주문은 직접 넣고 &lsquo;추매했어요&rsquo;로 기록하면 여윳돈에서 빠져요.
      </p>

      {plans.map((plan) => (
        <DipBuyPlanView
          key={plan.id}
          plan={plan}
          resetPct={resetPct}
          onEdit={() => setEditing(plan)}
        />
      ))}

      {plans.length === 0 && (
        <EmptyState
          title="아직 추매 안내를 켜지 않았어요"
          description="여윳돈과 구간을 정하면 적립일 1~3일 전과 당일 아침에 추매 금액·종목을 알려드려요."
          compact
        />
      )}

      {portfolioOptions.length > 0 && (
        <button
          type="button"
          onClick={() => setEditing("new")}
          className={`${TOUCH_TARGET_MIN} w-full rounded-lg border border-dashed border-gray-300 dark:border-gray-600 text-sm text-blue-600 dark:text-blue-400 hover:bg-gray-50 dark:hover:bg-gray-800`}
        >
          {plans.length === 0 ? "추매 안내 켜기" : "다른 포트폴리오에 추매 안내 추가"}
        </button>
      )}

      {editing && (
        <DipBuySettingsModal
          plan={editing === "new" ? null : editing}
          portfolioOptions={portfolioOptions}
          defaultPortfolioId={defaultPortfolioId}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

function DipBuyPlanView({
  plan,
  resetPct,
  onEdit,
}: {
  plan: DipBuyPlan;
  resetPct: number;
  onEdit: () => void;
}) {
  const qc = useQueryClient();
  const amountId = useId();
  const [confirming, setConfirming] = useState(false);
  const [amount, setAmount] = useState("");
  const completeMutation = useMutation({
    mutationFn: (amountKrw: number | null) => completeDipBuy(plan.portfolio_id, amountKrw),
    onSuccess: () => {
      void invalidateDipBuyData(qc);
      toast("추매를 기록했어요 — 여윳돈에서 뺐습니다", "success");
      setConfirming(false);
    },
    onError: (e) => toast(extractErrorMessage(e, "기록에 실패했습니다"), "error"),
  });

  const due = plan.due_amount_krw > 0;
  const amountValue = amount.trim() === "" ? null : Number(amount.replace(/,/g, ""));
  const amountInvalid = amountValue != null && !(amountValue > 0);

  return (
    <section className="rounded-xl border border-gray-200 dark:border-gray-700 p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 break-keep">
            {plan.portfolio_name}
            {!plan.is_active && (
              <span className="ml-2 text-xs font-normal text-gray-400">알림 꺼짐</span>
            )}
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {plan.index_ticker} 52주 고점 대비{" "}
            <span className="font-medium text-blue-600 dark:text-blue-400">
              {fmtDrawdown(plan.drawdown_pct)}
            </span>
            {" · "}남은 여윳돈 {fmtKrw(plan.reserve_krw)}
          </p>
          {plan.next_run_date && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {plan.is_run_day ? "오늘 적립일" : `다음 적립일 ${runDateLabel(plan.next_run_date)}`}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onEdit}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} shrink-0 text-xs text-blue-500 dark:text-blue-400 hover:underline`}
        >
          설정
        </button>
      </div>

      <ul className="divide-y divide-gray-100 dark:divide-gray-700 text-sm">
        {plan.tiers.map((t) => {
          const badge = STATE_LABEL[t.state];
          return (
            <li key={t.tier} className="flex items-center justify-between gap-2 py-2">
              <span className="text-gray-700 dark:text-gray-300">
                −{t.drawdown_pct}% · 여윳돈 {t.ratio_pct}%
              </span>
              <span className="flex items-center gap-2">
                <span className="text-gray-800 dark:text-gray-200">
                  {fmtKrw(t.done_amount_krw ?? t.amount_krw)}
                </span>
                <span className={`rounded-full px-2 py-0.5 text-xs ${badge.className}`}>
                  {badge.text}
                </span>
              </span>
            </li>
          );
        })}
      </ul>

      {!plan.has_dca_schedule && (
        <p className="text-xs text-amber-700 dark:text-amber-300 break-keep">
          이 포트폴리오에 정기 적립식 자동매수가 없어 적립일·종목을 정할 수 없어요.{" "}
          <Link
            to={rebalancingUrl({
              tab: "포트폴리오",
              portfolioId: plan.portfolio_id,
              openAlert: "dca",
            })}
            className="underline"
          >
            자동매수 설정
          </Link>
        </p>
      )}

      {due ? (
        <div className="rounded-lg bg-amber-50 dark:bg-amber-950/30 p-3 space-y-2">
          <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">
            {plan.is_run_day ? "오늘" : "이번 적립일에"} 추매 {fmtKrw(plan.due_amount_krw)}
          </p>
          {plan.items.length > 0 ? (
            <ul className="space-y-1 text-xs text-gray-700 dark:text-gray-300">
              {plan.items.map((item) => (
                <li key={item.ticker} className="flex justify-between gap-2">
                  <span className="min-w-0 truncate">
                    {item.name} {item.shares.toLocaleString()}주
                  </span>
                  <span className="shrink-0">
                    {fmtKrw(item.amount_krw)}
                    {isOverseasMarket(item.market) && item.amount_usd != null && (
                      <> (약 {fmtUsdPrice(item.amount_usd)})</>
                    )}
                  </span>
                </li>
              ))}
              {plan.leftover_krw > 0 && (
                <li className="text-gray-500 dark:text-gray-400">
                  1주 단위로 나누고 남은 {fmtKrw(plan.leftover_krw)}
                </li>
              )}
            </ul>
          ) : (
            plan.has_dca_schedule && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                종목별 수량을 계산하지 못했어요. 평소 적립 비율대로 나눠 사세요.
              </p>
            )
          )}
          <button
            type="button"
            onClick={() => {
              setAmount(String(Math.round(plan.due_amount_krw)));
              setConfirming(true);
            }}
            className={`${TOUCH_TARGET_MIN} w-full bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700`}
          >
            추매했어요
          </button>
        </div>
      ) : (
        <p className="text-xs text-gray-500 dark:text-gray-400 break-keep">
          {plan.drawdown_pct == null
            ? "지수 낙폭을 확인하지 못해 이번엔 안내하지 않아요."
            : `지금은 추매할 구간이 없어요. 고점 대비 −${resetPct}% 이내로 회복하면 완료 기록을 지우고 다음 하락을 기다려요.`}
        </p>
      )}

      {confirming && (
        <ConfirmModal
          message="실제로 산 금액을 확인해주세요. 이번 구간을 완료로 기록하고 여윳돈에서 뺍니다."
          confirmLabel={completeMutation.isPending ? "기록 중..." : "기록하기"}
          danger={false}
          onConfirm={() => {
            if (amountInvalid) return;
            completeMutation.mutate(amountValue);
          }}
          onCancel={() => setConfirming(false)}
        >
          <div className="mt-3">
            <label htmlFor={amountId} className={FORM_LABEL}>
              산 금액 (원)
            </label>
            <input
              id={amountId}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              inputMode="numeric"
              className={`${INPUT_SM} w-full`}
            />
            <p
              className={`mt-1 text-xs ${amountInvalid ? "text-red-600 dark:text-red-400" : "text-gray-500 dark:text-gray-400"}`}
            >
              {amountInvalid
                ? "0보다 큰 금액을 입력해주세요"
                : amountValue != null
                  ? fmtKrwPreview(amountValue)
                  : "비워 두면 안내 금액으로 기록해요"}
            </p>
          </div>
        </ConfirmModal>
      )}
    </section>
  );
}
