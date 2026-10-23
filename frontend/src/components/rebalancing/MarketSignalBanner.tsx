import { useState } from "react";
import { Bell, ChevronDown } from "lucide-react";
import { Link } from "react-router-dom";
import type { MarketSignalResponse, MarketRiskLevel } from "@/api/marketSignals";
import type { InflationIndicatorSummary } from "@/api/economicIndicators";
import { buildSignalRows } from "@/utils/marketSignalRows";
import { useCompositeSignalToggle } from "@/hooks/useCompositeSignalToggle";
import MarketSignalLevelBadge from "./MarketSignalLevelBadge";
import SignalRow from "./SignalRow";
import InflationIndicatorList from "./InflationIndicatorList";
import { TOUCH_TARGET_MIN_MOBILE_ONLY, TOUCH_TARGET_ROW } from "@/constants/uiSizes";

interface Props {
  signal: MarketSignalResponse;
  /** 미국 물가 지표 — 지정 시 상세 영역 하단에 함께 표시(별도 카드 대신, U9) */
  inflation?: InflationIndicatorSummary[];
  /** 지정 시 상세 영역 하단에 "목표 조정 › 전술" 이동 안내 — 이 신호로 목표 비중 자체를 바꾸는 곳 */
  onOpenTactical?: () => void;
}

const BANNER_BG: Record<MarketRiskLevel, string> = {
  GREEN: "bg-green-50 border-green-200 dark:bg-green-950/40 dark:border-green-800/40",
  YELLOW: "bg-yellow-50 border-yellow-200 dark:bg-yellow-950/40 dark:border-yellow-800/40",
  RED: "bg-red-50 border-red-200 dark:bg-red-950/40 dark:border-red-800/40",
};

const SHORT_IMPLICATION: Record<MarketRiskLevel, string> = {
  GREEN: "계획대로 진행",
  YELLOW: "분할 집행 권장",
  RED: "포지션 점검 필요",
};

function scoreColor(level: MarketRiskLevel): string {
  if (level === "GREEN") return "text-green-600 dark:text-green-400";
  if (level === "YELLOW") return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

export default function MarketSignalBanner({ signal, inflation, onOpenTactical }: Props) {
  const {
    composite_level,
    composite_score,
    composite_score_max,
    data_freshness,
    signals,
    confirmed_level,
  } = signal;
  // 표시 등급은 즉시, 자동 실행 판단 등급은 연속 확인 후 바뀐다 — 다를 때만 알려 "배너는 위험인데 자동 실행이
  // 돌았다"는 혼란을 막는다(plans/63 P1-5)
  const gateLagging = !!confirmed_level && confirmed_level !== composite_level;
  // 등급 배지 + 한 줄 요약이 기본 — 비GREEN이면 자동으로 8행 상세가 펼쳐져 진단 탭이 길어졌다(plans/64 S4)
  const [isOpen, setIsOpen] = useState(false);

  const rows = buildSignalRows(signals);
  const tierA = rows.filter((r) => r.tier === "A");
  const tierRest = rows.filter((r) => r.tier !== "A");
  const [macroOpen, setMacroOpen] = useState(tierRest.some((r) => (r.content?.subScore ?? 0) > 0));

  const { status: compositeStatus } = useCompositeSignalToggle();

  return (
    <div className={`rounded-xl border ${BANNER_BG[composite_level]}`}>
      {/* 헤더 */}
      <div className="px-4 py-3 flex items-center gap-2 flex-wrap">
        <span className="text-xs font-medium text-gray-600 dark:text-gray-300 shrink-0">
          시장 위험 신호
        </span>
        <MarketSignalLevelBadge level={composite_level} />
        <span className="text-xs text-gray-500 dark:text-gray-400 order-last basis-full sm:order-none sm:basis-auto sm:flex-1 sm:min-w-0 sm:truncate">
          {SHORT_IMPLICATION[composite_level]}
          {data_freshness === "STALE" && " · 데이터 조회 불가"}
          {data_freshness === "PARTIAL" && " · 일부 데이터 없음"}
        </span>
        <span className={`text-xs font-semibold shrink-0 ${scoreColor(composite_level)}`}>
          위험지수 {composite_score}/{composite_score_max ?? 27}
        </span>
        <button
          onClick={() => setIsOpen((v) => !v)}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} gap-0.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 shrink-0 transition-colors ml-1`}
          aria-expanded={isOpen}
          aria-label="시장 신호 상세 보기"
        >
          {isOpen ? "접기" : "자세히"}
          <ChevronDown
            size={11}
            className={`transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
          />
        </button>
      </div>

      {gateLagging && confirmed_level && (
        <div className="px-4 pb-2.5 -mt-1 flex items-center gap-1.5 flex-wrap text-xs text-gray-500 dark:text-gray-400">
          <span>자동 실행 판단 기준은 아직</span>
          <MarketSignalLevelBadge level={confirmed_level} />
          <span>— 같은 등급이 연속 확인되면 반영돼요</span>
        </div>
      )}

      {/* 상세 내용 */}
      {isOpen && (
        <div className="px-4 pb-3 space-y-2.5 border-t border-inherit pt-2.5">
          {tierA.map((row) => (
            <SignalRow key={row.key} label={row.label} content={row.content} />
          ))}

          <button
            onClick={() => setMacroOpen((v) => !v)}
            className={`${TOUCH_TARGET_ROW} gap-0.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors`}
            aria-expanded={macroOpen}
          >
            매크로 지표 {tierRest.length}개 {macroOpen ? "접기" : "더보기"}
            <ChevronDown
              size={11}
              className={`transition-transform duration-200 ${macroOpen ? "rotate-180" : ""}`}
            />
          </button>

          {macroOpen && (
            <div className="space-y-2.5">
              {tierRest.map((row) => (
                <SignalRow key={row.key} label={row.label} content={row.content} />
              ))}
            </div>
          )}

          {inflation && inflation.length > 0 && (
            <div className="pt-2.5 border-t border-inherit">
              <InflationIndicatorList data={inflation} />
            </div>
          )}

          {onOpenTactical && (
            <button
              type="button"
              onClick={onOpenTactical}
              className={`${TOUCH_TARGET_ROW} gap-0.5 text-xs text-blue-600 dark:text-blue-400 hover:underline`}
            >
              이 신호로 QQQ·SPY 비중을 조절하려면 → 목표 조정 › 전술
            </button>
          )}
        </div>
      )}

      {/* 시장 위험 신호 알림 현황 — 읽기 전용 한 줄(켜기/끄기는 설정 페이지가 단일 소스). 상시 3줄+링크였던 것을
          상태 한 줄로 줄이고, 설명은 알림이 실제로 발동했을 때의 사유만 남긴다 (docs/plans/67 P1-9) */}
      {compositeStatus && (
        <div className="px-4 py-1 border-t border-inherit bg-gray-50/80 dark:bg-gray-900/40 rounded-b-xl">
          <div className="flex items-center gap-2">
            <Bell size={13} className="text-gray-400 shrink-0" />
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300 shrink-0">
              시장 위험 신호 알림
            </span>
            <span
              className={`text-xs font-semibold shrink-0 ${compositeStatus.enabled ? "text-blue-600 dark:text-blue-400" : "text-gray-500 dark:text-gray-400"}`}
            >
              {compositeStatus.enabled ? "받는 중" : "꺼짐"}
            </span>
            <Link
              to="/settings/notifications?atab=시장 신호 알림"
              aria-label="시장 위험 신호 알림 설정"
              className={`${TOUCH_TARGET_ROW} !justify-end ml-auto text-xs text-blue-600 dark:text-blue-400`}
            >
              설정 →
            </Link>
          </div>
          {compositeStatus.triggered && compositeStatus.reason && (
            <p className="text-xs text-gray-500 dark:text-gray-400 ml-5 pb-1.5">
              {compositeStatus.reason}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
