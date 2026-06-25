import { useState } from "react";
import { ChevronDown, Calendar, TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { MacroDiagnosisResponse, CpiDirection, GrowthBias } from "@/api/marketSignals";

interface Props {
  diagnosis: MacroDiagnosisResponse;
}

const BIAS_BG: Record<GrowthBias, string> = {
  bullish: "bg-blue-50 border-blue-200 dark:bg-blue-950/40 dark:border-blue-800/40",
  neutral: "bg-gray-50 border-gray-200 dark:bg-gray-800/40 dark:border-gray-700/40",
  bearish: "bg-orange-50 border-orange-200 dark:bg-orange-950/40 dark:border-orange-800/40",
};

const BIAS_BADGE: Record<GrowthBias, string> = {
  bullish: "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300",
  neutral: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
  bearish: "bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300",
};

const BIAS_LABEL: Record<GrowthBias, string> = {
  bullish: "성장주 유리",
  neutral: "중립",
  bearish: "성장주 주의",
};

const CPI_DOT: Record<CpiDirection, string> = {
  rising: "bg-orange-500",
  flat: "bg-gray-400",
  falling: "bg-green-500",
};

const CPI_COLOR: Record<CpiDirection, string> = {
  rising: "text-orange-600 dark:text-orange-400",
  flat: "text-gray-500 dark:text-gray-400",
  falling: "text-green-600 dark:text-green-400",
};

const CPI_LABEL: Record<CpiDirection, string> = {
  rising: "상승",
  flat: "보합",
  falling: "하락",
};

const CPI_ICON = {
  rising: TrendingUp,
  flat: Minus,
  falling: TrendingDown,
} as const;

const FED_DIR_LABEL: Record<string, string> = {
  rising: "인상 추세",
  stable: "유지",
  falling: "인하 추세",
};

export default function MacroDiagnosisCard({ diagnosis }: Props) {
  const { cpi, fed_rate, fomc, implication, data_freshness } = diagnosis;
  const bias = implication?.growth_bias ?? "neutral";
  const [isOpen, setIsOpen] = useState(bias !== "bullish");

  const isStale = data_freshness === "STALE";
  const CpiIcon = cpi ? CPI_ICON[cpi.direction] : Minus;

  return (
    <div className={`rounded-xl border ${BIAS_BG[bias]}`}>
      {/* 헤더 */}
      <div className="px-4 py-3 flex items-center gap-2">
        <span className="text-xs font-medium text-gray-600 dark:text-gray-300 shrink-0">거시경제 진단</span>
        {implication && (
          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${BIAS_BADGE[bias]}`}>
            {BIAS_LABEL[bias]}
          </span>
        )}
        <span className="text-xs text-gray-500 dark:text-gray-400 flex-1 min-w-0 truncate">
          {isStale
            ? "데이터 조회 불가"
            : implication
              ? `${implication.label} · ${implication.action}`
              : "분석 중"}
        </span>
        <button
          onClick={() => setIsOpen((v) => !v)}
          className="flex items-center gap-0.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 shrink-0 transition-colors ml-1"
          aria-expanded={isOpen}
          aria-label="거시경제 진단 상세 보기"
        >
          {isOpen ? "접기" : "자세히"}
          <ChevronDown size={11} className={`transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
        </button>
      </div>

      {/* 상세 내용 */}
      {isOpen && (
        <div className="px-4 pb-3 space-y-2.5 border-t border-inherit pt-2.5">
          {/* CPI */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">CPI 동향</span>
            {cpi ? (
              <>
                <span className={`w-2 h-2 rounded-full shrink-0 ${CPI_DOT[cpi.direction]}`} />
                <span className={`text-xs font-medium ${CPI_COLOR[cpi.direction]}`}>
                  <CpiIcon size={11} className="inline mr-0.5 -mt-0.5" />
                  {CPI_LABEL[cpi.direction]}
                </span>
                <span className="text-xs text-gray-700 dark:text-gray-300 ml-1">
                  {cpi.latest_value.toFixed(1)}
                  {cpi.yoy_pct !== null && (
                    <span className="text-gray-400 dark:text-gray-500"> · 전년비 {cpi.yoy_pct > 0 ? "+" : ""}{cpi.yoy_pct.toFixed(1)}%</span>
                  )}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-400">—</span>
            )}
          </div>

          {/* 기준금리 */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">기준금리</span>
            {fed_rate ? (
              <>
                <span className={`w-2 h-2 rounded-full shrink-0 ${fed_rate.is_high ? "bg-orange-500" : "bg-green-500"}`} />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  {fed_rate.latest_value.toFixed(2)}% · {FED_DIR_LABEL[fed_rate.direction]}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
                  {fed_rate.is_high ? "고금리 수준" : "저금리 수준"}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-400">—</span>
            )}
          </div>

          {/* 다음 FOMC */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">다음 FOMC</span>
            {fomc.next_meeting_date ? (
              <>
                <Calendar size={11} className="text-gray-400 shrink-0" />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  {fomc.next_meeting_date}
                </span>
                {fomc.days_until !== null && (
                  <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
                    D-{fomc.days_until}일
                    {fomc.source === "fallback" && " *"}
                  </span>
                )}
              </>
            ) : (
              <span className="text-xs text-gray-400">일정 미확인</span>
            )}
          </div>

          {/* 진단 메시지 */}
          {implication && !isStale && (
            <div className={`mt-1 px-3 py-2.5 rounded-lg border ${BIAS_BG[bias]}`}>
              <p className="text-xs text-gray-700 dark:text-gray-300 leading-relaxed">
                {implication.message}
              </p>
              <div className="mt-1.5 flex items-center gap-1.5">
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${BIAS_BADGE[bias]}`}>
                  {implication.action}
                </span>
                {fomc.source === "fallback" && (
                  <span className="text-xs text-gray-400">* 예정 일정 기준</span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
