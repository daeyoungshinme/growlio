import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  completeDipBuy,
  DIP_BUY_INDEX_LABEL,
  DIP_BUY_INDEXES,
  DIP_BUY_VS_TACTICAL_NOTE,
  type DipBuyEtf,
  type DipBuyIndex,
  type DipBuyRule,
  type DipBuyStatus,
  type DipBuyTierState,
} from "@/api/dipBuy";
import InfoTip from "@/components/common/InfoTip";
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
import { fmtKrw, fmtKrwPreview, fmtKrwPrice, fmtUsdPrice, parseYmd } from "@/utils/format";
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

/** 그 구간에 닿을 때 ETF별 예상 1주가 — 해외는 달러(실환율일 때), 국내·환율 없음은 원화 */
function tierSharePrices(etfs: readonly DipBuyEtf[], tier: number): string[] {
  return etfs.flatMap((etf) => {
    const krw = etf.tier_price_krw?.[tier];
    if (krw == null) return [];
    const usd = isOverseasMarket(etf.market) ? etf.tier_price_usd?.[tier] : undefined;
    return [`${etf.name} 약 ${usd != null ? fmtUsdPrice(usd) : fmtKrwPrice(krw)}`];
  });
}

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
  // 기존 규칙 편집 또는 { index } = 그 지수 규칙 새로 추가
  const [editingRule, setEditingRule] = useState<DipBuyRule | { index: DipBuyIndex } | null>(null);

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
  const ruleByIndex = new Map(rules.map((r) => [r.index_ticker, r]));
  const editing = editingRule && "id" in editingRule ? editingRule : null;

  return (
    <div className="space-y-4">
      {/* 첫 문장만 — 쓰는 법·전술 웅덩이와의 구분은 탭해서 보기(plans/150 C2·C3) */}
      <p className="text-xs text-gray-500 dark:text-gray-400 break-keep">
        매달 적립은 그대로 두고, 모아 둔 여윳돈을 지수가 52주 고점 대비 내려간 구간마다 나눠 사도록
        알려드려요.
        <InfoTip
          label="낙폭 추매 안내 설명"
          className="ml-0.5 align-middle"
          content={
            <>
              적립금을 줄여 모은 돈이 아니라 원래 투자하지 않던 여윳돈일 때 쓰세요. 주문은 직접 넣고
              &lsquo;추매했어요&rsquo;로 기록하면 여윳돈에서 빠져요. {DIP_BUY_VS_TACTICAL_NOTE}
            </>
          }
        />
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

      {/* 지수마다 항상 한 칸 — 규칙이 없는 지수도 낙폭과 추가 버튼을 보여준다 */}
      {DIP_BUY_INDEXES.map((index) => {
        const rule = ruleByIndex.get(index);
        return rule ? (
          <DipBuyRuleView
            key={index}
            rule={rule}
            resetPct={resetPct}
            hasCandidates={data?.has_candidates ?? false}
            onEdit={() => setEditingRule(rule)}
          />
        ) : (
          <DipBuyEmptyIndex
            key={index}
            index={index}
            drawdownPct={data?.index_drawdowns?.[index] ?? null}
            canAdd={settings != null}
            onAdd={() => setEditingRule({ index })}
          />
        );
      })}

      {editingSettings && (
        <DipBuySettingsModal settings={settings} onClose={() => setEditingSettings(false)} />
      )}
      {editingRule && (
        <DipBuyRuleModal
          rule={editing}
          initialIndex={"index" in editingRule ? editingRule.index : undefined}
          availableIndexes={availableIndexes}
          otherRules={rules.filter((r) => r.id !== editing?.id)}
          poolKrw={poolKrw}
          onClose={() => setEditingRule(null)}
        />
      )}
    </div>
  );
}

function DipBuyEmptyIndex({
  index,
  drawdownPct,
  canAdd,
  onAdd,
}: {
  index: DipBuyIndex;
  drawdownPct: number | null;
  canAdd: boolean;
  onAdd: () => void;
}) {
  return (
    <section className="rounded-xl border border-dashed border-gray-300 dark:border-gray-600 p-4 space-y-2">
      <div className="min-w-0">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 break-keep">
          {DIP_BUY_INDEX_LABEL[index]}
          <span className="ml-2 text-xs font-normal text-gray-400">규칙 없음</span>
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          52주 고점 대비{" "}
          <span className="font-medium text-blue-600 dark:text-blue-400">
            {fmtDrawdown(drawdownPct)}
          </span>
        </p>
      </div>
      {canAdd ? (
        <button
          type="button"
          onClick={onAdd}
          aria-label={`${DIP_BUY_INDEX_LABEL[index]} 규칙 추가`}
          className={`${TOUCH_TARGET_MIN} w-full rounded-lg text-sm text-blue-600 dark:text-blue-400 hover:bg-gray-50 dark:hover:bg-gray-800`}
        >
          규칙 추가
        </button>
      ) : (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          여윳돈을 먼저 정하면 규칙을 추가할 수 있어요.
        </p>
      )}
    </section>
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
          const prices = tierSharePrices(rule.etfs, t.tier);
          return (
            <li key={t.tier} className="py-2">
              <div className="flex items-center justify-between gap-2">
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
              </div>
              {prices.length > 0 && (
                <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400 break-keep">
                  1주 {prices.join(" · ")}
                </p>
              )}
            </li>
          );
        })}
      </ul>
      {rule.etfs.some((e) => (e.tier_price_krw?.length ?? 0) > 0) && (
        <p className="text-xs text-gray-400 dark:text-gray-500 break-keep">
          구간별 1주 가격은 지금 낙폭과 현재가로 계산한 추정이에요(국내 상장 ETF는 환율 변동
          미반영).
        </p>
      )}

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
              <ul className="space-y-2 text-xs text-gray-700 dark:text-gray-300">
                {rule.etfs.map((etf) => {
                  const overseas = isOverseasMarket(etf.market);
                  return (
                    <li key={`${etf.ticker}:${etf.market}`}>
                      <div className="flex justify-between gap-2">
                        <span className="min-w-0 truncate">
                          {etf.name} {etf.shares.toLocaleString()}주
                        </span>
                        <span className="shrink-0">
                          {fmtKrw(etf.amount_krw)}
                          {overseas && etf.amount_usd != null && (
                            <> (약 {fmtUsdPrice(etf.amount_usd)})</>
                          )}
                        </span>
                      </div>
                      <p className="text-gray-500 dark:text-gray-400">
                        1주{" "}
                        {overseas && etf.price_usd != null
                          ? `${fmtUsdPrice(etf.price_usd)} · ${fmtKrwPrice(etf.price_krw)}`
                          : fmtKrwPrice(etf.price_krw)}
                      </p>
                    </li>
                  );
                })}
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
