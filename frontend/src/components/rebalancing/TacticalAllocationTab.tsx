import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { TacticalStatus } from "@/api/tactical";
import EmptyState from "@/components/common/EmptyState";
import SkeletonCard from "@/components/common/SkeletonCard";
import { ToggleSwitch } from "@/components/common/ToggleSwitch";
import ErrorBoundary from "@/components/ErrorBoundary";
import { LABEL_SM, SELECT_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { useDcaTacticalLink } from "@/hooks/useDcaTacticalLink";
import { useTacticalMutations, useTacticalStatus } from "@/hooks/useTacticalAllocation";
import { extractErrorMessage } from "@/utils/error";
import { localToday, parseYmd } from "@/utils/format";
import { toast } from "@/utils/toast";
import { useAutoExecutionNotice } from "@/hooks/useAutoExecutionNotice";
import TacticalApplyConfirmModal from "./TacticalApplyConfirmModal";
import { DcaTacticalNotice, TacticalRegimeCard, WeightsCompare } from "./TacticalStatusParts";
import TacticalWeightsEditor from "./TacticalWeightsEditor";
import {
  REGIME_LABEL,
  TACTICAL_ASSET_LIST_TEXT,
  TACTICAL_ASSETS,
  tacticalNextAction,
} from "./tacticalLabels";
import { portfoliosQuery } from "@/api/queryOptions";

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

/** "YYYY-MM-DD" → "M/D" */
function fmtMd(ymd: string): string {
  const { month, day } = parseYmd(ymd);
  return `${month}/${day}`;
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
  const { dcaAuto, linked } = useDcaTacticalLink(status.portfolio_id);
  const nextAction = tacticalNextAction(status, fullyApplied, undefined, { dcaLinked: linked });

  return (
    <>
      <TacticalRegimeCard status={status} nextAction={nextAction} />

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

        <DcaTacticalNotice portfolioId={status.portfolio_id} dcaAuto={dcaAuto} linked={linked} />

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
                className={
                  linked
                    ? `${TOUCH_TARGET_MIN} px-5 rounded-lg text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 disabled:opacity-50`
                    : `${TOUCH_TARGET_MIN} bg-blue-600 text-white px-5 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`
                }
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
              onClick={() => disable.mutate({ dcaLinked: linked })}
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
        <TacticalApplyConfirmModal
          status={{ ...status, proposed_weights: status.proposed_weights }}
          partialActive={partialActive}
          autoExecutionNotice={autoExecutionNotice}
          pending={apply.isPending}
          onClose={() => setConfirmApply(false)}
          onApply={runApply}
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

/** 리밸런싱 페이지 "목표 조정 › 전술" 모드 — 포트폴리오를 골라 QQQ/SPY(+DIA·QLD·SSO) 전술 배분 국면·제안 비중을 보고 적용한다. */
export default function TacticalAllocationTab({
  selectedPortfolioId,
  onSelectPortfolio,
  onGoToExecution,
  onCreatePortfolio,
  showPortfolioPicker = true,
}: Props) {
  const { data: portfolios, isLoading: portfoliosLoading } = useQuery(portfoliosQuery);
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
          description="나스닥·S&P500 비중을 관리할 포트폴리오를 먼저 만들어주세요."
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
      {/* key — 포트폴리오를 바꾸면 확인창·"방금 적용" 상태를 버린다. 남으면 열린 확인창이 다른 포트폴리오에
          적용되거나 새 포트폴리오가 이미 적용된 것처럼 보였다 (plans/62 F1·77 C1) */}
      {status && (
        <TacticalStatusView
          key={status.portfolio_id}
          status={status}
          onGoToExecution={onGoToExecution}
        />
      )}
    </div>
  );
}
