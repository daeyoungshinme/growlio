import { useState } from "react";
import { Bell, ChevronDown } from "lucide-react";
import { Link } from "react-router-dom";
import type { MarketSignalResponse, MarketRiskLevel } from "@/api/marketSignals";
import { buildSignalRows } from "@/utils/marketSignalRows";
import { useCompositeSignalToggle } from "@/hooks/useCompositeSignalToggle";
import MarketSignalLevelBadge from "./MarketSignalLevelBadge";
import SignalRow from "./SignalRow";

interface Props {
  signal: MarketSignalResponse;
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

export default function MarketSignalBanner({ signal }: Props) {
  const { composite_level, composite_score, composite_score_max, data_freshness, signals } = signal;
  const [isOpen, setIsOpen] = useState(composite_level !== "GREEN");

  const rows = buildSignalRows(signals);
  const tierA = rows.filter((r) => r.tier === "A");
  const tierRest = rows.filter((r) => r.tier !== "A");
  const [macroOpen, setMacroOpen] = useState(tierRest.some((r) => (r.content?.subScore ?? 0) > 0));

  const { status: compositeStatus } = useCompositeSignalToggle();

  return (
    <div className={`rounded-xl border ${BANNER_BG[composite_level]}`}>
      {/* 헤더 */}
      <div className="px-4 py-3 flex items-center gap-2">
        <span className="text-xs font-medium text-gray-600 dark:text-gray-300 shrink-0">
          시장 위험 신호
        </span>
        <MarketSignalLevelBadge level={composite_level} />
        <span className="text-xs text-gray-500 dark:text-gray-400 flex-1 min-w-0 truncate">
          {SHORT_IMPLICATION[composite_level]}
          {data_freshness === "STALE" && " · 데이터 조회 불가"}
          {data_freshness === "PARTIAL" && " · 일부 데이터 없음"}
        </span>
        <span className={`text-xs font-semibold shrink-0 ${scoreColor(composite_level)}`}>
          위험지수 {composite_score}/{composite_score_max ?? 27}
        </span>
        <button
          onClick={() => setIsOpen((v) => !v)}
          className="flex items-center gap-0.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 shrink-0 transition-colors ml-1"
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

      {/* 상세 내용 */}
      {isOpen && (
        <div className="px-4 pb-3 space-y-2.5 border-t border-inherit pt-2.5">
          {tierA.map((row) => (
            <SignalRow key={row.key} label={row.label} content={row.content} />
          ))}

          <button
            onClick={() => setMacroOpen((v) => !v)}
            className="flex items-center gap-0.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
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
        </div>
      )}

      {/* 시장 위험 신호 알림 현황 — isOpen 상태와 무관하게 항상 표시. 읽기 전용(켜기/끄기는 설정 페이지가 단일 소스),
          배너 상태색과 분리된 중립 배경으로 "알림 영역"임을 구분 */}
      {compositeStatus && (
        <div className="flex flex-col gap-1 px-4 py-2.5 border-t border-inherit bg-gray-50/80 dark:bg-gray-900/40 rounded-b-xl">
          <div className="flex items-center gap-2">
            <Bell size={13} className="text-gray-400 shrink-0" />
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300 shrink-0">
              시장 위험 신호 알림
            </span>
            <span
              className={`text-xs font-semibold shrink-0 ml-auto ${compositeStatus.enabled ? "text-blue-600 dark:text-blue-400" : "text-gray-400 dark:text-gray-500"}`}
            >
              {compositeStatus.enabled ? "받는 중" : "꺼짐"}
            </span>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 ml-5">
            {compositeStatus.triggered && compositeStatus.reason
              ? compositeStatus.reason
              : compositeStatus.enabled
                ? "이탈이 없어도 시장/리스크가 위험 수준이면 알림을 보내드려요"
                : "알림이 꺼져 있어 신호를 평가하지 않습니다"}
          </p>
          <Link
            to="/settings/notifications?atab=시장 신호 알림"
            className="text-xs text-blue-600 dark:text-blue-400 underline self-start ml-5"
          >
            설정에서 켜기/끄기 →
          </Link>
        </div>
      )}
    </div>
  );
}
