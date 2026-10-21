import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchPortfolios } from "@/api/portfolios";
import type { TacticalStatus, TacticalWeights, TechnicalSnapshot } from "@/api/tactical";
import ConfirmModal from "@/components/common/ConfirmModal";
import EmptyState from "@/components/common/EmptyState";
import SkeletonCard from "@/components/common/SkeletonCard";
import { ToggleSwitch } from "@/components/common/ToggleSwitch";
import ErrorBoundary from "@/components/ErrorBoundary";
import { LABEL_SM, SELECT_SM } from "@/constants/inputStyles";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { useTacticalMutations, useTacticalStatus } from "@/hooks/useTacticalAllocation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";
import MarketSignalLevelBadge from "./MarketSignalLevelBadge";
import { useAutoExecutionNotice } from "@/hooks/useAutoExecutionNotice";
import TacticalWeightsEditor from "./TacticalWeightsEditor";
import {
  ASSET_LABEL,
  REGIME_BADGE_CLASS,
  REGIME_LABEL,
  TACTICAL_ASSETS,
  TILT_LABEL,
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

/** 백엔드 tactical_allocation_service.format_weights와 같은 규칙 — DIA는 0%면 생략 */
function formatWeights(weights: TacticalWeights): string {
  return TACTICAL_ASSETS.filter((a) => a !== "DIA" || (weights[a] ?? 0) > 0)
    .map((a) => `${a === "CASH" ? "현금" : a} ${weights[a] ?? 0}%`)
    .join(" · ");
}

function fmtNum(n: number | null | undefined, digits = 2): string {
  return n == null ? "—" : n.toFixed(digits);
}

function IndicatorRow({
  ticker,
  snap,
  note,
}: {
  ticker: string;
  snap?: TechnicalSnapshot;
  note?: string;
}) {
  const trend = snap?.trend ?? "UNKNOWN";
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
        <span className={`text-sm font-medium ${trendCls}`}>추세 {TREND_LABEL[trend]}</span>
      </div>
      <dl className="mt-1 grid grid-cols-3 gap-x-3 gap-y-0.5 text-xs text-gray-600 dark:text-gray-300">
        <div>
          <dt className="text-gray-400 dark:text-gray-500">종가</dt>
          <dd>${fmtNum(snap?.close)}</dd>
        </div>
        <div>
          <dt className="text-gray-400 dark:text-gray-500">50일선</dt>
          <dd>${fmtNum(snap?.sma50)}</dd>
        </div>
        <div>
          <dt className="text-gray-400 dark:text-gray-500">200일선</dt>
          <dd>${fmtNum(snap?.sma200)}</dd>
        </div>
        <div>
          <dt className="text-gray-400 dark:text-gray-500">RSI(14)</dt>
          <dd>{fmtNum(snap?.rsi14, 1)}</dd>
        </div>
        <div>
          <dt className="text-gray-400 dark:text-gray-500">MACD 히스토그램</dt>
          <dd>{fmtNum(snap?.macd_hist)}</dd>
        </div>
        <div>
          <dt className="text-gray-400 dark:text-gray-500">52주 고점 대비</dt>
          <dd>{snap?.drawdown_pct == null ? "—" : `${snap.drawdown_pct.toFixed(1)}%`}</dd>
        </div>
      </dl>
    </div>
  );
}

function TiltSummary({ status }: { status: TacticalStatus }) {
  const off = status.tilt_shift_pct <= 0;
  return (
    <div className="border-t border-gray-100 dark:border-gray-700 pt-2 flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold">나스닥·S&P 비중</span>
        <span className="text-sm font-medium">
          {off
            ? "조절 안 함"
            : `${TILT_LABEL[status.confirmed_tilt]}${status.confirmed_tilt === "BALANCED" ? "" : ` (${status.tilt_shift_pct}%p 이동)`}`}
        </span>
      </div>
      {!off && (
        <ul className="text-xs text-gray-500 dark:text-gray-400 list-disc pl-4 space-y-0.5">
          {status.tilt_reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
          {status.enabled && status.observed_tilt !== status.confirmed_tilt && (
            <li className="text-amber-600 dark:text-amber-400">
              오늘 판단은 {TILT_LABEL[status.observed_tilt]} — 다음 달 첫 점검일에 반영돼요
            </li>
          )}
        </ul>
      )}
    </div>
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
          // DIA는 선택 자산 — 현재·제안 모두 0이면 행을 숨긴다
          if (a === "DIA" && cur === 0 && next === 0) return null;
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
  const [justApplied, setJustApplied] = useState(false);
  const autoExecutionNotice = useAutoExecutionNotice(status.portfolio_id);
  const regime = status.confirmed_regime ?? status.observed_regime;
  const alreadyApplied =
    status.applied_regime != null &&
    status.applied_regime === status.confirmed_regime &&
    TACTICAL_ASSETS.every(
      (a) => (status.current_weights[a] ?? 0) === (status.proposed_weights?.[a] ?? 0),
    );

  return (
    <>
      <section className="card flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">QQQ·SPY 전술 배분</h2>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              국면에 맞는 새 목표 비중을 제안해요. 적용해도 주문은 나가지 않아요.
            </p>
          </div>
          {regime ? (
            <span
              className={`shrink-0 px-3 py-1 rounded-full border text-sm font-semibold ${REGIME_BADGE_CLASS[regime]}`}
            >
              {REGIME_LABEL[regime]}
            </span>
          ) : (
            <span className="shrink-0 text-sm text-gray-500 dark:text-gray-400">판정 불가</span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
          <span>매크로(확정)</span>
          <MarketSignalLevelBadge level={status.macro_level} />
          {/* 모바일은 title 툴팁이 안 뜬다 — 진단 탭 배지와 등급이 다를 수 있는 이유를 화면에 적는다 */}
          <span className="basis-full text-gray-500 dark:text-gray-400">
            진단 탭 시장 신호를 연속 확인한 등급이라 진단 탭보다 늦게 바뀔 수 있어요
          </span>
          {status.macro_freshness === "STALE" && (
            <span className="text-amber-600 dark:text-amber-400">지표 데이터 지연</span>
          )}
          {status.enabled && status.pending_regime && (
            <span className="text-amber-600 dark:text-amber-400">
              {REGIME_LABEL[status.pending_regime]} 전환 확인 중(다음 거래일 재확인)
            </span>
          )}
        </div>
        <ul className="text-xs text-gray-500 dark:text-gray-400 list-disc pl-4 space-y-0.5">
          {status.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>

        <div>
          <IndicatorRow ticker="QQQ" snap={status.technicals.QQQ} />
          <IndicatorRow ticker="SPY" snap={status.technicals.SPY} />
          <IndicatorRow ticker="DIA" snap={status.technicals.DIA} note="참고 · 국면 판단 미반영" />
        </div>
        <TiltSummary status={status} />
      </section>

      <section className="card flex flex-col gap-3">
        <h2 className="text-base font-semibold">
          {regime ? `${REGIME_LABEL[regime]} 국면 제안 비중` : "제안 비중"}
        </h2>
        <WeightsCompare status={status} />
        {!status.portfolio_compatible && (
          <p className="text-xs text-amber-700 dark:text-amber-400">
            이 포트폴리오에는 QQQ·SPY·DIA·현금 외 종목이 있어요. 적용하면 그 종목들은 목표 비중에서
            빠져요.
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
                  })
                }
                ariaLabel="국면 전환 알림"
              />
            </div>
            {justApplied || alreadyApplied ? (
              <button
                type="button"
                className={`${TOUCH_TARGET_MIN} bg-blue-600 text-white px-5 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors`}
                onClick={() => onGoToExecution(status.portfolio_id)}
              >
                리밸런싱 분석·실행으로 이동
              </button>
            ) : (
              <button
                type="button"
                className={`${TOUCH_TARGET_MIN} bg-blue-600 text-white px-5 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`}
                disabled={!status.confirmed_regime || apply.isPending}
                onClick={() => setConfirmApply(true)}
              >
                제안 비중을 목표 비중으로 적용
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
          과거 데이터 기반 참고 신호이며 수익을 보장하지 않아요.{" "}
          {autoExecutionNotice
            ? "이 포트폴리오는 자동 실행이 켜져 있어 적용한 비중이 다음 자동 실행에 반영돼요."
            : "주문은 리밸런싱 화면에서 직접 확인 후 실행돼요."}
        </p>
      </section>

      {status.enabled && (
        <TacticalWeightsEditor
          key={`${JSON.stringify(status.regime_weights)}:${status.tilt_shift_pct}`}
          regimeWeights={status.regime_weights}
          isDefaultWeights={status.is_default_weights}
          tiltShiftPct={status.tilt_shift_pct}
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
        <ConfirmModal
          message={`"${status.portfolio_name}" 목표 비중을 ${REGIME_LABEL[status.confirmed_regime ?? "NEUTRAL"]} 국면 비중(${formatWeights(status.proposed_weights)})으로 바꿀까요? ${autoExecutionNotice ?? "주문은 나가지 않으며, 다음 화면에서 매매 내역을 확인한 뒤 직접 실행해요."}${status.portfolio_compatible ? "" : " QQQ·SPY·DIA·현금 외 종목은 목표에서 빠집니다."}`}
          confirmLabel="적용"
          danger={false}
          onCancel={() => setConfirmApply(false)}
          onConfirm={() => {
            setConfirmApply(false);
            apply.mutate(undefined, { onSuccess: () => setJustApplied(true) });
          }}
        />
      )}

      <ErrorBoundary variant="section">
        <Suspense fallback={<SkeletonCard rows={1} />}>
          <TacticalBacktestSection portfolioId={status.portfolio_id} />
        </Suspense>
      </ErrorBoundary>
    </>
  );
}

/** 리밸런싱 페이지 "목표 조정 › 전술" 모드 — 포트폴리오를 골라 QQQ/SPY(+DIA) 전술 배분 국면·제안 비중을 보고 적용한다. */
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
