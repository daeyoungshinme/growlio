import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ListChecks } from "lucide-react";
import { fetchPortfolios } from "@/api/portfolios";
import type { TacticalStatus, TechnicalSnapshot } from "@/api/tactical";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import Modal, { ModalFooter } from "@/components/common/Modal";
import EmptyState from "@/components/common/EmptyState";
import SkeletonCard from "@/components/common/SkeletonCard";
import { ToggleSwitch } from "@/components/common/ToggleSwitch";
import ErrorBoundary from "@/components/ErrorBoundary";
import { LABEL_SM, SELECT_SM } from "@/constants/inputStyles";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { useCollapsible } from "@/hooks/useCollapsible";
import { useTacticalMutations, useTacticalStatus } from "@/hooks/useTacticalAllocation";
import { extractErrorMessage } from "@/utils/error";
import { localToday, parseYmd } from "@/utils/format";
import { toast } from "@/utils/toast";
import MarketSignalLevelBadge from "./MarketSignalLevelBadge";
import { useAutoExecutionNotice } from "@/hooks/useAutoExecutionNotice";
import TacticalWeightsEditor from "./TacticalWeightsEditor";
import {
  ASSET_LABEL,
  formatTacticalWeights,
  type NextActionTone,
  OPTIONAL_ASSETS,
  PULLBACK_BADGE_CLASS,
  PULLBACK_LABEL,
  REGIME_BADGE_CLASS,
  REGIME_LABEL,
  regimeDayCount,
  TACTICAL_ASSET_LIST_TEXT,
  TACTICAL_ASSETS,
  tacticalNextAction,
  TILT_LABEL,
  TRANSITION_CONFIRM_NOTE,
  TREND_LABEL,
} from "./tacticalLabels";

const TacticalBacktestSection = lazy(() => import("./TacticalBacktestSection"));

interface Props {
  /** 페이지에서 고른 포트폴리오(URL portfolioId) — 탭 간 선택을 공유한다(plans/63 P3-3) */
  selectedPortfolioId?: string;
  /** 포트폴리오 변경 시 호출 — 부모가 URL에 반영한다. 없으면 이 탭 안에서만 바뀐다 */
  onSelectPortfolio?: (portfolioId: string) => void;
  /** 제안 비중 적용 후 기존 리밸런싱 분석·실행 화면으로 이동 */
  onGoToExecution: (portfolioId: string) => void;
  /** 포트폴리오가 없을 때 빈 상태 CTA — 새 포트폴리오 편집기를 연다 */
  onCreatePortfolio?: () => void;
  /** false면 이 탭의 포트폴리오 select를 숨긴다 — 목표 조정 탭이 상단 공용 선택기를 그릴 때(plans/64 S2) */
  showPortfolioPicker?: boolean;
}

const NEXT_ACTION_CLASS: Record<NextActionTone, string> = {
  action: "bg-blue-50 text-blue-800 dark:bg-blue-900/20 dark:text-blue-200",
  wait: "bg-amber-50 text-amber-800 dark:bg-amber-900/20 dark:text-amber-200",
  idle: "bg-gray-50 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
};

function fmtNum(n: number | null | undefined, digits = 2): string {
  return n == null ? "—" : n.toFixed(digits);
}

/** 종가의 이평선 대비 이격(%) — 음수면 이평선 아래(웅덩이) */
function fmtGap(close: number | null | undefined, ma: number | null | undefined): string {
  if (close == null || ma == null || ma <= 0) return "—";
  const pct = (close / ma - 1) * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

/** "YYYY-MM-DD" → "M/D" */
function fmtMd(ymd: string): string {
  const { month, day } = parseYmd(ymd);
  return `${month}/${day}`;
}

function IndicatorRow({
  ticker,
  snap,
  note,
  showPullback = false,
}: {
  ticker: string;
  snap?: TechnicalSnapshot;
  note?: string;
  /** 웅덩이 배지 — 투입 판정 기준인 QQQ에만 단다(SPY·DIA는 이격 수치만) */
  showPullback?: boolean;
}) {
  const trend = snap?.trend ?? "UNKNOWN";
  const stage = snap?.pullback_stage;
  const trendCls =
    trend === "UP"
      ? "text-red-500"
      : trend === "DOWN"
        ? "text-blue-500"
        : "text-gray-500 dark:text-gray-400";
  return (
    <div className="py-2 border-t border-gray-100 dark:border-gray-700 first:border-t-0">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">
          {ticker}
          {note && (
            <span className="ml-1.5 text-xs font-normal text-gray-400 dark:text-gray-500">
              {note}
            </span>
          )}
        </span>
        <span className="flex items-center gap-2">
          {showPullback && stage && stage !== "UNKNOWN" && (
            <span className={`px-2 py-0.5 rounded-full text-xs ${PULLBACK_BADGE_CLASS[stage]}`}>
              {PULLBACK_LABEL[stage]}
            </span>
          )}
          <span className={`text-sm font-medium ${trendCls}`}>추세 {TREND_LABEL[trend]}</span>
        </span>
      </div>
      <dl className="mt-1 grid grid-cols-3 gap-x-3 gap-y-0.5 text-xs text-gray-600 dark:text-gray-300">
        <div>
          <dt className="text-gray-400 dark:text-gray-500">종가</dt>
          <dd>${fmtNum(snap?.close)}</dd>
        </div>
        <div>
          <dt className="text-gray-400 dark:text-gray-500">RSI(14)</dt>
          <dd>{fmtNum(snap?.rsi14, 1)}</dd>
        </div>
        <div>
          <dt className="text-gray-400 dark:text-gray-500">52주 고점 대비</dt>
          <dd>{snap?.drawdown_pct == null ? "—" : `${snap.drawdown_pct.toFixed(1)}%`}</dd>
        </div>
        {/* 이평선은 절대 가격 대신 종가 이격으로 — 어느 선까지 눌렸는지(웅덩이 깊이)가 한눈에 보이게 */}
        {(
          [
            ["20일선", snap?.sma20],
            ["60일선", snap?.sma60],
            ["120일선", snap?.sma120],
            ["200일선", snap?.sma200],
          ] as const
        ).map(([label, ma]) => (
          <div key={label}>
            <dt className="text-gray-400 dark:text-gray-500">{label} 대비</dt>
            <dd>{fmtGap(snap?.close, ma)}</dd>
          </div>
        ))}
        <div>
          <dt className="text-gray-400 dark:text-gray-500">MACD 히스토그램</dt>
          <dd>{fmtNum(snap?.macd_hist)}</dd>
        </div>
      </dl>
    </div>
  );
}

/** 요약 한 줄(제목 + 값) — 근거 목록은 "판정 근거·차트 지표" 접힘 안에 둔다 */
function SummaryLine({ title, value }: { title: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-sm font-semibold">{title}</span>
      <span className="text-sm font-medium text-right">{value}</span>
    </div>
  );
}

function tiltValue(status: TacticalStatus): string {
  if (status.tilt_shift_pct <= 0) return "조절 안 함";
  return `${TILT_LABEL[status.confirmed_tilt]}${status.confirmed_tilt === "BALANCED" ? "" : ` (${status.tilt_shift_pct}%p 이동)`}`;
}

function dipValue(status: TacticalStatus): string {
  if (status.dip_shift_pct <= 0) return "사용 안 함";
  if (status.dip_deployed_pct > 0) return `현금 ${status.dip_deployed_pct}%p 투입 중`;
  // 단계는 진행 중인데 옮길 현금이 없는 비중표(현금 0%)
  return status.dip_level > 0 ? "투입할 현금 없음" : "대기";
}

function ReasonList({ items }: { items: string[] }) {
  return (
    <ul className="text-xs text-gray-500 dark:text-gray-400 list-disc pl-4 space-y-0.5">
      {items.map((r) => (
        <li key={r}>{r}</li>
      ))}
    </ul>
  );
}

/** 판정 근거(매크로·추세)·차트 지표·틸트/웅덩이 근거 — 모바일 길이를 줄이려 기본 접힘(plans/69 P4) */
function TacticalDetails({ status }: { status: TacticalStatus }) {
  const [isOpen, toggle] = useCollapsible(false, "growlio:rebalancing:tactical-details-open");
  // DIA는 비중표 어느 국면에든 쓰일 때만 참고 지표로 보여준다
  const usesDia =
    Object.values(status.regime_weights).some((w) => (w.DIA ?? 0) > 0) ||
    (status.current_weights.DIA ?? 0) > 0;
  const tiltOn = status.tilt_shift_pct > 0;
  return (
    <CollapsibleCard
      icon={ListChecks}
      title="판정 근거·차트 지표"
      isOpen={isOpen}
      onToggle={toggle}
      cardClassName="border-t border-gray-100 dark:border-gray-700 pt-1"
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
          {status.use_macro ? (
            <>
              <span>매크로(확정)</span>
              <MarketSignalLevelBadge level={status.macro_level} />
              {status.macro_freshness === "STALE" && (
                <span className="text-amber-600 dark:text-amber-400">지표 데이터 지연</span>
              )}
              {/* 모바일은 title 툴팁이 안 뜬다 — 진단 탭 배지와 등급이 다를 수 있는 이유를 화면에 적는다 */}
              <span className="basis-full text-gray-500 dark:text-gray-400">
                연속 확인한 등급이라 진단 탭보다 늦게 바뀔 수 있어요
              </span>
            </>
          ) : (
            <span>매크로 반영 안 함 — SPY·QQQ 200일선 추세만으로 판단해요</span>
          )}
        </div>
        <ReasonList items={status.reasons} />
        <div>
          <IndicatorRow ticker="QQQ" snap={status.technicals.QQQ} showPullback />
          <IndicatorRow ticker="SPY" snap={status.technicals.SPY} />
          {usesDia && (
            <IndicatorRow
              ticker="DIA"
              snap={status.technicals.DIA}
              note="참고 · 국면 판단 미반영"
            />
          )}
        </div>
        {tiltOn && (
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">
              나스닥·S&P 비중 근거
            </span>
            <ReasonList items={status.tilt_reasons} />
            {status.enabled && status.observed_tilt !== status.confirmed_tilt && (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                오늘 판단은 {TILT_LABEL[status.observed_tilt]} — 다음 달 첫 점검일에 반영돼요
              </p>
            )}
          </div>
        )}
        <div className="flex flex-col gap-1">
          <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">
            웅덩이 매수 근거
          </span>
          <ReasonList
            items={
              status.dip_shift_pct > 0
                ? status.dip_reasons
                : [
                    ...status.dip_reasons,
                    "비중표 편집에서 켜면 공격 국면의 눌림목에 현금 일부를 주식으로 옮겨요.",
                  ]
            }
          />
        </div>
      </div>
    </CollapsibleCard>
  );
}

function WeightsCompare({ status }: { status: TacticalStatus }) {
  const proposed = status.proposed_weights;
  const otherCurrent = Object.entries(status.current_weights)
    .filter(([t]) => !(TACTICAL_ASSETS as string[]).includes(t))
    .reduce((sum, [, w]) => sum + w, 0);
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-xs text-gray-500 dark:text-gray-400 text-left">
          <th className="py-1 font-medium">자산</th>
          <th className="py-1 font-medium text-right">현재 목표</th>
          <th className="py-1 font-medium text-right">제안</th>
        </tr>
      </thead>
      <tbody>
        {TACTICAL_ASSETS.map((a) => {
          const cur = status.current_weights[a] ?? 0;
          const next = proposed?.[a] ?? 0;
          // DIA·QLD·SSO는 선택 자산 — 현재·제안 모두 0이면 행을 숨긴다
          if (OPTIONAL_ASSETS.has(a) && cur === 0 && next === 0) return null;
          return (
            <tr key={a} className="border-t border-gray-100 dark:border-gray-700">
              <td className="py-1.5">{ASSET_LABEL[a]}</td>
              <td className="py-1.5 text-right">{cur}%</td>
              <td
                className={`py-1.5 text-right font-semibold ${cur !== next ? "text-blue-600 dark:text-blue-400" : ""}`}
              >
                {proposed ? `${next}%` : "—"}
              </td>
            </tr>
          );
        })}
        {otherCurrent > 0 && (
          <tr className="border-t border-gray-100 dark:border-gray-700 text-gray-500 dark:text-gray-400">
            <td className="py-1.5">기타 종목</td>
            <td className="py-1.5 text-right">{otherCurrent}%</td>
            <td className="py-1.5 text-right">0%</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function TacticalStatusView({
  status,
  onGoToExecution,
}: {
  status: TacticalStatus;
  onGoToExecution: (portfolioId: string) => void;
}) {
  const { upsert, disable, apply } = useTacticalMutations(status.portfolio_id);
  const [confirmApply, setConfirmApply] = useState(false);
  // 이번 화면에서 방금 적용한 비율(1=전체, 0.5=절반) — 서버 재조회 전에도 다음 단계 버튼을 보여주려고
  const [justApplied, setJustApplied] = useState<number | null>(null);
  const runApply = (fraction: number) => {
    setConfirmApply(false);
    apply.mutate(fraction, { onSuccess: () => setJustApplied(fraction) });
  };
  const autoExecutionNotice = useAutoExecutionNotice(status.portfolio_id);
  const regime = status.confirmed_regime ?? status.observed_regime;
  const alreadyApplied =
    status.applied_regime != null &&
    status.applied_regime === status.confirmed_regime &&
    TACTICAL_ASSETS.every(
      (a) => (status.current_weights[a] ?? 0) === (status.proposed_weights?.[a] ?? 0),
    );
  const partialActive =
    status.partial_regime != null && status.partial_regime === status.confirmed_regime;
  const fullyApplied = alreadyApplied || justApplied === 1;
  const showGoToExecution = fullyApplied || justApplied != null || partialActive;
  const nextAction = tacticalNextAction(status, fullyApplied);
  const days = status.enabled ? regimeDayCount(status.regime_changed_at) : null;
  const hints = status.transition_hints.slice(0, 2);

  return (
    <>
      <section className="card flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          {/* "주문은 나가지 않아요"는 목표 조정 탭 상단 안내가 이미 말한다 — 반복 제거 (docs/plans/67 P1-8) */}
          <h2 className="text-base font-semibold">QQQ·SPY 전술 배분</h2>
          {regime ? (
            <span className="shrink-0 flex flex-col items-end gap-0.5">
              <span
                className={`px-3 py-1 rounded-full border text-sm font-semibold ${REGIME_BADGE_CLASS[regime]}`}
              >
                {status.enabled ? REGIME_LABEL[regime] : `${REGIME_LABEL[regime]} (오늘 관측)`}
              </span>
              {days != null && status.confirmed_regime && (
                <span className="text-xs text-gray-500 dark:text-gray-400">{days}일째</span>
              )}
            </span>
          ) : (
            <span className="shrink-0 text-sm text-gray-500 dark:text-gray-400">판정 불가</span>
          )}
        </div>

        <p
          className={`rounded-lg px-3 py-2 text-sm font-medium ${NEXT_ACTION_CLASS[nextAction.tone]}`}
        >
          {nextAction.text}
        </p>

        {hints.length > 0 && (
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">
              다음 전환 조건
            </span>
            <ReasonList items={hints.map((h) => h.text)} />
            <p className="text-xs text-gray-400 dark:text-gray-500">{TRANSITION_CONFIRM_NOTE}</p>
          </div>
        )}

        <div className="border-t border-gray-100 dark:border-gray-700 pt-2 flex flex-col gap-1">
          <SummaryLine title="나스닥·S&P 비중" value={tiltValue(status)} />
          <SummaryLine title="웅덩이 매수(눌림목)" value={dipValue(status)} />
        </div>

        <TacticalDetails status={status} />
      </section>

      <section className="card flex flex-col gap-3">
        <h2 className="text-base font-semibold">
          {regime ? `${REGIME_LABEL[regime]} 국면 제안 비중` : "제안 비중"}
        </h2>
        <WeightsCompare status={status} />
        {!status.portfolio_compatible && (
          <p className="text-xs text-amber-700 dark:text-amber-400">
            이 포트폴리오에는 {TACTICAL_ASSET_LIST_TEXT} 외 종목이 있어요. 적용하면 그 종목들은 목표
            비중에서 빠져요.
          </p>
        )}

        {!status.enabled ? (
          <button
            type="button"
            className={`${TOUCH_TARGET_MIN} bg-blue-600 text-white px-5 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`}
            disabled={upsert.isPending}
            onClick={() => upsert.mutate({ notify_enabled: true })}
          >
            전술 배분 켜기 (국면 전환 시 알림)
          </button>
        ) : (
          <>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm">국면 전환 알림 (이메일·푸시)</span>
              <ToggleSwitch
                checked={status.notify_enabled}
                disabled={upsert.isPending}
                onChange={(checked) =>
                  upsert.mutate({
                    notify_enabled: checked,
                    regime_weights: status.is_default_weights ? null : status.regime_weights,
                    tilt_shift_pct: status.tilt_shift_pct,
                    dip_shift_pct: status.dip_shift_pct,
                    use_macro: status.use_macro,
                  })
                }
                ariaLabel="국면 전환 알림"
              />
            </div>
            {!fullyApplied && (
              <button
                type="button"
                className={`${TOUCH_TARGET_MIN} bg-blue-600 text-white px-5 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`}
                disabled={!status.confirmed_regime || apply.isPending}
                onClick={() => setConfirmApply(true)}
              >
                {partialActive ? "나머지 적용" : "제안 비중을 목표 비중으로 적용"}
              </button>
            )}
            {partialActive && status.partial_applied_on && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {status.partial_applied_on === localToday()
                  ? "오늘"
                  : fmtMd(status.partial_applied_on)}{" "}
                절반 적용 · 다음 거래일 이후 나머지 적용을 권장해요
              </p>
            )}
            {showGoToExecution && (
              <button
                type="button"
                className={
                  fullyApplied
                    ? `${TOUCH_TARGET_MIN} bg-blue-600 text-white px-5 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors`
                    : `${TOUCH_TARGET_MIN} px-5 rounded-lg text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200`
                }
                onClick={() => onGoToExecution(status.portfolio_id)}
              >
                리밸런싱 분석·실행으로 이동
              </button>
            )}
            <button
              type="button"
              className={`${TOUCH_TARGET_MIN} text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200`}
              disabled={disable.isPending}
              onClick={() => disable.mutate()}
            >
              전술 배분 끄기
            </button>
          </>
        )}
        <p className="text-xs text-gray-400 dark:text-gray-500">
          과거 데이터 기반 참고 신호이며 수익을 보장하지 않아요.
          {autoExecutionNotice &&
            " 이 포트폴리오는 자동 실행이 켜져 있어 적용한 비중이 다음 자동 실행에 반영돼요."}
        </p>
      </section>

      {status.enabled && (
        <TacticalWeightsEditor
          key={`${JSON.stringify(status.regime_weights)}:${status.tilt_shift_pct}:${status.dip_shift_pct}:${status.use_macro}`}
          regimeWeights={status.regime_weights}
          isDefaultWeights={status.is_default_weights}
          tiltShiftPct={status.tilt_shift_pct}
          dipShiftPct={status.dip_shift_pct}
          useMacro={status.use_macro}
          notifyEnabled={status.notify_enabled}
          saving={upsert.isPending}
          onSave={(payload) =>
            upsert.mutate(payload, {
              onSuccess: () => toast("비중표를 저장했습니다", "success"),
            })
          }
        />
      )}

      {confirmApply && status.proposed_weights && (
        <Modal
          title={partialActive ? "나머지 적용" : "제안 비중 적용"}
          size="sm"
          onClose={() => setConfirmApply(false)}
        >
          <div className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-2 text-sm text-gray-700 dark:text-gray-200">
            <p>
              &ldquo;{status.portfolio_name}&rdquo; 목표 비중을{" "}
              {REGIME_LABEL[status.confirmed_regime ?? "NEUTRAL"]} 국면 비중(
              {formatTacticalWeights(status.proposed_weights)})으로 {partialActive ? "마저 " : ""}
              바꿀까요?
            </p>
            <p className="text-gray-500 dark:text-gray-400">
              {autoExecutionNotice ??
                "주문은 나가지 않으며, 다음 화면에서 매매 내역을 확인한 뒤 직접 실행해요."}
              {!status.portfolio_compatible &&
                ` ${TACTICAL_ASSET_LIST_TEXT} 외 종목은 목표에서 빠집니다.`}
            </p>
            {status.portfolio_compatible && !partialActive && (
              <p className="text-gray-500 dark:text-gray-400">
                국면이 막 바뀐 직후라면 절반만 먼저 적용하고 다음 거래일에 나머지를 적용해 매수·매도
                타이밍을 나눌 수 있어요.
              </p>
            )}
          </div>
          <ModalFooter>
            {status.portfolio_compatible && !partialActive && (
              <button
                type="button"
                className={`${TOUCH_TARGET_MIN} flex-1 px-4 rounded-lg text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 disabled:opacity-50`}
                disabled={apply.isPending}
                onClick={() => runApply(0.5)}
              >
                절반 먼저 적용
              </button>
            )}
            <button
              type="button"
              className={`${TOUCH_TARGET_MIN} flex-1 bg-blue-600 text-white px-4 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`}
              disabled={apply.isPending}
              onClick={() => runApply(1)}
            >
              {partialActive ? "나머지 적용" : "한 번에 적용"}
            </button>
          </ModalFooter>
        </Modal>
      )}

      <ErrorBoundary variant="section">
        <Suspense fallback={<SkeletonCard rows={1} />}>
          <TacticalBacktestSection portfolioId={status.portfolio_id} />
        </Suspense>
      </ErrorBoundary>
    </>
  );
}

/** 리밸런싱 페이지 "목표 조정 › 전술" 모드 — 포트폴리오를 골라 QQQ/SPY(+DIA·QLD·SSO) 전술 배분 국면·제안 비중을 보고 적용한다. */
export default function TacticalAllocationTab({
  selectedPortfolioId,
  onSelectPortfolio,
  onGoToExecution,
  onCreatePortfolio,
  showPortfolioPicker = true,
}: Props) {
  const { data: portfolios, isLoading: portfoliosLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
    staleTime: STALE_TIME.MEDIUM,
  });
  // 부모가 URL로 관리하면(onSelectPortfolio) URL이 단일 진실, 아니면 탭 내부 상태
  const [localPickedId, setLocalPickedId] = useState<string | undefined>(selectedPortfolioId);
  const pickedId = onSelectPortfolio ? selectedPortfolioId : localPickedId;
  const setSelectedId = (id: string) =>
    onSelectPortfolio ? onSelectPortfolio(id) : setLocalPickedId(id);
  // 선택값이 목록에 없으면(미지정·삭제됨) 첫 포트폴리오 — effect로 setState하지 않고 렌더 중 파생
  const selectedId = portfolios?.some((p) => p.id === pickedId) ? pickedId : portfolios?.[0]?.id;

  const { data: status, isLoading, isError, error, refetch } = useTacticalStatus(selectedId);

  if (portfoliosLoading) return <SkeletonCard />;
  if (!portfolios?.length) {
    return (
      <div className="card">
        <EmptyState
          title="포트폴리오가 없어요"
          description="QQQ·SPY 비중을 관리할 포트폴리오를 먼저 만들어주세요."
          action={
            onCreatePortfolio
              ? { label: "포트폴리오 만들기", onClick: onCreatePortfolio }
              : undefined
          }
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {showPortfolioPicker && (
        <label className="flex flex-col gap-1 px-1">
          <span className={LABEL_SM}>전술 배분을 적용할 포트폴리오</span>
          <select
            className={SELECT_SM}
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(e.target.value)}
          >
            {portfolios.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {isLoading && <SkeletonCard rows={4} />}
      {isError && (
        <div className="card flex flex-col gap-2">
          <p className="text-sm text-gray-600 dark:text-gray-300">
            {extractErrorMessage(error, "전술 배분 정보를 불러오지 못했습니다")}
          </p>
          <button
            type="button"
            className={`${TOUCH_TARGET_MIN} text-sm text-blue-600 dark:text-blue-400`}
            onClick={() => refetch()}
          >
            다시 시도
          </button>
        </div>
      )}
      {status && <TacticalStatusView status={status} onGoToExecution={onGoToExecution} />}
    </div>
  );
}
