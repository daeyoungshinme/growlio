import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  completeDipBuy,
  DIP_BUY_INDEX_LABEL,
  DIP_BUY_INDEXES,
  type DipBuyRule,
  type DipBuyStatus,
  type DipBuyTierState,
} from "@/api/dipBuy";
import { dipBuyQuery } from "@/api/queryOptions";
import EmptyState from "@/components/common/EmptyState";
import SkeletonCard from "@/components/common/SkeletonCard";
import ConfirmModal from "@/components/common/ConfirmModal";
import DipBuySettingsModal from "@/components/invest/DipBuySettingsModal";
import DipBuyRuleModal from "@/components/invest/DipBuyRuleModal";
import { FORM_LABEL, INPUT_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_MIN, TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { isOverseasMarket } from "@/constants/markets";
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
    text: "지금 추매",
    className: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
  },
  WAITING: {
    text: "대기",
    className: "bg-gray-50 text-gray-500 dark:bg-gray-900 dark:text-gray-400",
  },
};

const WEEKDAYS = "일월화수목금토";

function dateLabel(ymd: string): string {
  const { year, month, day } = parseYmd(ymd);
  const weekday = WEEKDAYS[new Date(year, month - 1, day).getDay()] ?? "";
  return `${month}월 ${day}일(${weekday})`;
}

const fmtDrawdown = (pct: number | null) => (pct == null ? "확인 불가" : `${pct.toFixed(1)}%`);

function notifyLabel(data: DipBuyStatus): string {
  const s = data.settings;
  if (!s) return "";
  if (!s.is_active) return "알림 꺼짐";
  if (s.notify_mode === "ON_REACH") return "알림: 구간 도달 다음 날 아침";
  const next = data.next_notify_date ? ` · 다음 ${dateLabel(data.next_notify_date)}` : "";
  return `알림: 매달 ${s.notify_day}일${next}`;
}

/**
 * 계획 › 적립 계획 "낙폭 추매 안내"(plans/147·148) — 적립은 그대로, 사용자당 여윳돈 하나를 지수별 규칙 몫·낙폭
 * 구간으로 나눠 금액과 추천 후보 ETF별 수량을 안내. 포트폴리오와 무관, 주문 없음
 */
export default function DipBuyCard() {
  const { data, isLoading, isError, refetch } = useQuery(dipBuyQuery);
  const [editingSettings, setEditingSettings] = useState(false);
  const [editingRule, setEditingRule] = useState<DipBuyRule | "new" | null>(null);

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

  const settings = data?.settings ?? null;
  const rules = data?.rules ?? [];
  const resetPct = data?.reset_drawdown_pct ?? 3;
  const usedIndexes = new Set(rules.map((r) => r.index_ticker));
  const availableIndexes = DIP_BUY_INDEXES.filter((i) => !usedIndexes.has(i));
  const allocationTotal = rules.reduce((sum, r) => sum + r.allocation_pct, 0);
  const poolKrw = (settings?.reserve_krw ?? 0) + rules.reduce((sum, r) => sum + r.spent_krw, 0);
  const otherAllocation = (rule: DipBuyRule | null) =>
    rules.reduce((sum, r) => (r.id === rule?.id ? sum : sum + r.allocation_pct), 0);

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500 dark:text-gray-400 break-keep">
        매달 적립은 그대로 두고, 따로 모아 둔 여윳돈을 지수가 52주 고점 대비 내려간 구간마다 나눠
        사도록 알려드려요. 적립금을 줄여 모은 돈이 아니라 원래 투자하지 않던 여윳돈일 때 쓰세요.
        주문은 직접 넣고 &lsquo;추매했어요&rsquo;로 기록하면 여윳돈에서 빠져요. 전술 배분의 웅덩이
        매수(포트폴리오 안 현금 비중 조정)와는 별개예요.
      </p>

      {settings ? (
        <section className="flex items-start justify-between gap-2 rounded-xl bg-gray-50 dark:bg-gray-900/40 p-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">
              남은 여윳돈 {fmtKrw(settings.reserve_krw)}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {data && notifyLabel(data)}
              {rules.length > 0 && ` · 배분 ${allocationTotal}%`}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setEditingSettings(true)}
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} shrink-0 text-xs text-blue-500 dark:text-blue-400 hover:underline`}
          >
            설정
          </button>
        </section>
      ) : (
        <EmptyState
          title="아직 추매 여윳돈을 정하지 않았어요"
          description="여윳돈과 알림 시점을 정한 뒤 나스닥100·S&P500 규칙을 추가하면 추매 금액과 살 ETF를 알려드려요."
          action={{ label: "여윳돈 정하기", onClick: () => setEditingSettings(true) }}
          compact
        />
      )}

      {data && data.dca_held_portfolios.length > 0 && data.due_amount_krw > 0 && (
        <p className="rounded-lg bg-gray-50 dark:bg-gray-900/40 px-3 py-2 text-xs text-gray-600 dark:text-gray-300 break-keep">
          {data.dca_held_portfolios.join(", ")} 적립 자동매수는 전술 방어 국면이라 보류 중이에요.
          추매는 적립과 별개인 여윳돈 안내예요.{" "}
          <Link to={rebalancingUrl({ tab: "목표 조정", mode: "전술" })} className="underline">
            전술 국면 보기
          </Link>
        </p>
      )}

      {rules.map((rule) => (
        <DipBuyRuleView
          key={rule.id}
          rule={rule}
          resetPct={resetPct}
          hasCandidates={data?.has_candidates ?? false}
          onEdit={() => setEditingRule(rule)}
        />
      ))}

      {settings && availableIndexes.length > 0 && allocationTotal < 100 && (
        <button
          type="button"
          onClick={() => setEditingRule("new")}
          className={`${TOUCH_TARGET_MIN} w-full rounded-lg border border-dashed border-gray-300 dark:border-gray-600 text-sm text-blue-600 dark:text-blue-400 hover:bg-gray-50 dark:hover:bg-gray-800`}
        >
          {rules.length === 0 ? "추매 규칙 추가" : "다른 지수 규칙 추가"}
        </button>
      )}

      {editingSettings && (
        <DipBuySettingsModal settings={settings} onClose={() => setEditingSettings(false)} />
      )}
      {editingRule && (
        <DipBuyRuleModal
          rule={editingRule === "new" ? null : editingRule}
          availableIndexes={availableIndexes}
          otherAllocationPct={otherAllocation(editingRule === "new" ? null : editingRule)}
          poolKrw={poolKrw}
          onClose={() => setEditingRule(null)}
        />
      )}
    </div>
  );
}

function DipBuyRuleView({
  rule,
  resetPct,
  hasCandidates,
  onEdit,
}: {
  rule: DipBuyRule;
  resetPct: number;
  hasCandidates: boolean;
  onEdit: () => void;
}) {
  const qc = useQueryClient();
  const amountId = useId();
  const [confirming, setConfirming] = useState(false);
  const [amount, setAmount] = useState("");
  const completeMutation = useMutation({
    mutationFn: (amountKrw: number | null) => completeDipBuy(rule.id, amountKrw),
    onSuccess: () => {
      void invalidateDipBuyData(qc);
      toast("추매를 기록했어요 — 여윳돈에서 뺐습니다", "success");
      setConfirming(false);
    },
    onError: (e) => toast(extractErrorMessage(e, "기록에 실패했습니다"), "error"),
  });

  const due = rule.due_amount_krw > 0;
  const amountValue = amount.trim() === "" ? null : Number(amount.replace(/,/g, ""));
  const amountInvalid = amountValue != null && !(amountValue > 0);

  return (
    <section className="rounded-xl border border-gray-200 dark:border-gray-700 p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 break-keep">
            {DIP_BUY_INDEX_LABEL[rule.index_ticker]}
            {!rule.is_active && (
              <span className="ml-2 text-xs font-normal text-gray-400">사용 안 함</span>
            )}
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            52주 고점 대비{" "}
            <span className="font-medium text-blue-600 dark:text-blue-400">
              {fmtDrawdown(rule.drawdown_pct)}
            </span>
            {" · "}여윳돈 {rule.allocation_pct}% · 남은 몫 {fmtKrw(rule.remaining_krw)}
          </p>
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
        {rule.tiers.map((t) => {
          const badge = STATE_LABEL[t.state];
          return (
            <li key={t.tier} className="flex items-center justify-between gap-2 py-2">
              <span className="text-gray-700 dark:text-gray-300">
                −{t.drawdown_pct}% · 몫의 {t.ratio_pct}%
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

      {due ? (
        <div className="rounded-lg bg-amber-50 dark:bg-amber-950/30 p-3 space-y-2">
          <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">
            추매 {fmtKrw(rule.due_amount_krw)}
          </p>
          {rule.etfs.length > 0 ? (
            <>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                계좌에 맞는 ETF 하나로 사세요
              </p>
              <ul className="space-y-1 text-xs text-gray-700 dark:text-gray-300">
                {rule.etfs.map((etf) => (
                  <li key={`${etf.ticker}:${etf.market}`} className="flex justify-between gap-2">
                    <span className="min-w-0 truncate">
                      {etf.name} {etf.shares.toLocaleString()}주
                    </span>
                    <span className="shrink-0">
                      {fmtKrw(etf.amount_krw)}
                      {isOverseasMarket(etf.market) && etf.amount_usd != null && (
                        <> (약 {fmtUsdPrice(etf.amount_usd)})</>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-xs text-gray-500 dark:text-gray-400 break-keep">
              {hasCandidates
                ? "이 지수를 추종하는 추천 후보 ETF의 시세를 받지 못했어요. 금액만큼 직접 사세요."
                : "목표 조정 › 추천에서 이 지수를 추종하는 후보 ETF를 등록하면 수량을 계산해 드려요."}{" "}
              {!hasCandidates && (
                <Link to={rebalancingUrl({ tab: "목표 조정", mode: "추천" })} className="underline">
                  후보 ETF 관리
                </Link>
              )}
            </p>
          )}
          <button
            type="button"
            onClick={() => {
              setAmount(String(Math.round(rule.due_amount_krw)));
              setConfirming(true);
            }}
            className={`${TOUCH_TARGET_MIN} w-full bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700`}
          >
            추매했어요
          </button>
        </div>
      ) : (
        <p className="text-xs text-gray-500 dark:text-gray-400 break-keep">
          {rule.drawdown_pct == null
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
