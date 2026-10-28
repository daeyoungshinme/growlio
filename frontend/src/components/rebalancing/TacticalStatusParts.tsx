import { ListChecks } from "lucide-react";
import { Link } from "react-router-dom";
import type { TacticalAsset, TacticalStatus } from "@/api/tactical";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import { useCollapsible } from "@/hooks/useCollapsible";
import { rebalancingUrl } from "@/utils/rebalancingUrl";
import { TOUCH_TARGET_ROW } from "@/constants/uiSizes";
import MarketSignalLevelBadge from "./MarketSignalLevelBadge";
import {
  ASSET_LABEL,
  INDEX_GROUP_ASSETS,
  type NextActionTone,
  OPTIONAL_ASSETS,
  REGIME_BADGE_CLASS,
  REGIME_LABEL,
  regimeDayCount,
  TACTICAL_ASSETS,
  TILT_LABEL,
  TRANSITION_CONFIRM_NOTE,
} from "./tacticalLabels";

/** 전술 탭(`TacticalAllocationTab`)의 표시 조각 — 국면 카드·판정 근거·비중 비교표·적립 연동 안내 (plans/79 D2) */

const NEXT_ACTION_CLASS: Record<NextActionTone, string> = {
  action: "bg-blue-50 text-blue-800 dark:bg-blue-900/20 dark:text-blue-200",
  wait: "bg-amber-50 text-amber-800 dark:bg-amber-900/20 dark:text-amber-200",
  idle: "bg-gray-50 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
};

/** 요약 한 줄(제목 + 값) — 근거 목록은 "판정 근거" 접힘 안에 둔다 */
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

/** 판정 근거(매크로·추세)·틸트/웅덩이 근거 — 모바일 길이를 줄이려 기본 접힘(plans/69 P4).
 *  매크로·차트 지표 자체는 진단 탭 "시장 상황" 카드가 담당한다(plans/82) */
function TacticalDetails({ status }: { status: TacticalStatus }) {
  const [isOpen, toggle] = useCollapsible(false, "growlio:rebalancing:tactical-details-open");
  const tiltOn = status.tilt_shift_pct > 0;
  return (
    <CollapsibleCard
      icon={ListChecks}
      title="판정 근거"
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
            </>
          ) : (
            <span>매크로 반영 안 함 — SPY·QQQ 200일선 추세만으로 판단해요</span>
          )}
        </div>
        <ReasonList items={status.reasons} />
        <Link
          to={rebalancingUrl({ tab: "진단" })}
          className={`${TOUCH_TARGET_ROW} text-xs text-blue-600 dark:text-blue-400`}
        >
          매크로·차트 지표 자세히 보기 → 진단 › 시장 상황
        </Link>
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

/** 지수 그룹 자산 행 보조 문구 — 대표 종목·합산 종목 수, 그룹이 아직 없으면 적용 시 묶인다는 안내 (plans/76) */
function GroupNote({ asset, status }: { asset: TacticalAsset; status: TacticalStatus }) {
  if (!INDEX_GROUP_ASSETS.has(asset)) return null;
  const group = status.current_groups?.[asset];
  const text = group
    ? `대표 ${group.primary}${group.member_count > 0 ? ` · ${group.member_count}종목 합산` : ""}`
    : (status.proposed_weights?.[asset] ?? 0) > 0
      ? "적용하면 같은 지수 보유 종목을 묶어요"
      : null;
  if (!text) return null;
  return <span className="block text-xs text-gray-500 dark:text-gray-400">{text}</span>;
}

export function WeightsCompare({ status }: { status: TacticalStatus }) {
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
              <td className="py-1.5">
                {ASSET_LABEL[a]}
                <GroupNote asset={a} status={status} />
              </td>
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

/** 국면 배지·"지금 할 일"·다음 전환 조건·틸트/웅덩이 요약 + 판정 근거 접힘 */
export function TacticalRegimeCard({
  status,
  nextAction,
}: {
  status: TacticalStatus;
  nextAction: { tone: NextActionTone; text: string };
}) {
  const regime = status.confirmed_regime ?? status.observed_regime;
  const days = status.enabled ? regimeDayCount(status.regime_changed_at) : null;
  const hints = status.transition_hints.slice(0, 2);
  return (
    <section className="card flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        {/* "주문은 나가지 않아요"는 목표 조정 탭 상단 안내가 이미 말한다 — 반복 제거 (docs/plans/67 P1-8) */}
        <h2 className="text-base font-semibold">나스닥·S&P500 전술 배분</h2>
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
  );
}

/** 적립식 코어 + 전술 보조(plans/71) — 적립 자동매수 포트폴리오엔 비중 적용(매도)보다 매수 보류 연동을 권한다 */
export function DcaTacticalNotice({
  portfolioId,
  dcaAuto,
  linked,
}: {
  portfolioId: string;
  dcaAuto: boolean;
  linked: boolean;
}) {
  if (linked) {
    return (
      <p className="text-xs text-gray-500 dark:text-gray-400">
        적립 보조 모드 — 이 포트폴리오 자동매수는 전술 연동 중이라 방어 국면엔 매수만 보류해요. 제안
        비중 적용은 필요하지 않아요.
      </p>
    );
  }
  if (!dcaAuto) return null;
  return (
    <div className="rounded-lg bg-blue-50 dark:bg-blue-900/20 px-3 py-2 text-xs text-blue-900 dark:text-blue-100 flex flex-col gap-1">
      <p className="font-semibold">적립 자동매수 중인 포트폴리오예요</p>
      <p>
        제안 비중 적용은 매도·양도세가 생기고, 과거 20년 적립식에선 수익률을 연 2~4%p 낮췄어요.
        자동매수 설정의 &lsquo;전술 연동&rsquo;을 켜면 방어 국면에만 매수를 보류해요 (수익은 비슷,
        금융위기 때 낙폭 절반).
      </p>
      <Link
        to={rebalancingUrl({
          tab: "포트폴리오",
          portfolioId,
          openAlert: "1",
        })}
        className="self-start font-medium text-blue-700 dark:text-blue-300 underline"
      >
        자동매수 설정 열기
      </Link>
    </div>
  );
}
