import { useState } from "react";
import { ChevronDown, ChevronUp, Settings2, WandSparkles } from "lucide-react";
import type { DCASettings } from "@/api/invest";
import { TOUCH_HEIGHT_MIN, TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { fmtKrw } from "@/utils/format";

/** 계획 › 적립 계획 탭의 "적립 계획 설정" 요약 — 핵심 4개는 늘 보이고 나머지는 모바일에서 더보기. */
export default function DcaSettingsSummaryCard({
  settings: s,
  annualDepositGoal,
  retirementTargetYear,
  showNotConfigured,
  onOpenWizard,
  onOpenEdit,
}: {
  settings: DCASettings | undefined;
  annualDepositGoal: number | null;
  retirementTargetYear: number | null;
  /** 분석 응답은 왔지만 필수 설정이 비어 있을 때 */
  showNotConfigured: boolean;
  onOpenWizard: () => void;
  onOpenEdit: () => void;
}) {
  const [showAllStats, setShowAllStats] = useState(false);
  return (
    <div className="card">
      <div className="flex flex-wrap items-start justify-between gap-y-2 mb-3">
        <div className="shrink-0">
          <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide whitespace-nowrap">
            적립 계획 설정
          </h2>
        </div>
        <div className="shrink-0 flex items-center gap-2">
          <button
            onClick={onOpenWizard}
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} gap-2 px-4 py-2 text-sm font-medium text-blue-600 dark:text-blue-400 bg-white dark:bg-gray-900 border border-blue-200 dark:border-blue-800 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-950 transition-colors`}
          >
            <WandSparkles size={15} />
            가이드로 설정
          </button>
          <button
            onClick={onOpenEdit}
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors`}
          >
            <Settings2 size={15} />
            설정 편집
          </button>
        </div>
      </div>
      {/* 상시 안내 2문단(가이드 vs 편집 차이·홈 탭 안내)은 버튼 이름으로 충분해 제거 (docs/plans/67 P1-12) */}
      <div className="grid gap-4 grid-cols-2 sm:grid-cols-4 lg:grid-cols-7">
        {(
          [
            {
              label: "월 적립액",
              value: s?.monthly_deposit_amount ? fmtKrw(s.monthly_deposit_amount) : null,
              priority: true,
            },
            {
              label: "목표 연수익률",
              value: s?.goal_annual_return_pct ? `${s.goal_annual_return_pct}%` : null,
              priority: true,
            },
            {
              label: "목표 금액",
              value: s?.goal_amount ? fmtKrw(s.goal_amount) : null,
              priority: true,
            },
            {
              label: "연간 입금 목표",
              value: annualDepositGoal ? fmtKrw(annualDepositGoal) : null,
              priority: true,
            },
            {
              label: "투자 시작일",
              value: s?.goal_start_date ?? null,
              priority: false,
            },
            {
              label: "시작시점 자산",
              value: s?.goal_initial_amount ? fmtKrw(s.goal_initial_amount) : null,
              emptyLabel: "스냅샷 자동",
              priority: false,
            },
            {
              label: "은퇴 목표시점",
              value: retirementTargetYear ? `${retirementTargetYear}년` : null,
              priority: false,
            },
          ] as const
        ).map((stat) => (
          <div key={stat.label} className={stat.priority || showAllStats ? "" : "hidden sm:block"}>
            <p className="text-xs text-gray-500 dark:text-gray-400">{stat.label}</p>
            <p className="text-base font-bold text-gray-900 dark:text-gray-50 mt-0.5">
              {stat.value ?? (
                <span className="text-gray-400 dark:text-gray-500">
                  {"emptyLabel" in stat ? stat.emptyLabel : "미설정"}
                </span>
              )}
            </p>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() => setShowAllStats((v) => !v)}
        className={`sm:hidden mt-3 ${TOUCH_HEIGHT_MIN} flex items-center gap-1 text-xs font-medium text-blue-600 dark:text-blue-400`}
      >
        {showAllStats ? (
          <>
            접기 <ChevronUp size={13} />
          </>
        ) : (
          <>
            더보기 <ChevronDown size={13} />
          </>
        )}
      </button>
      {showNotConfigured && (
        <div className="mt-4 p-3 bg-yellow-50 dark:bg-yellow-950 rounded-lg text-sm text-yellow-800 dark:text-yellow-400">
          월 적립액, 목표 수익률, 목표 금액, 투자 시작일을 모두 설정해야 분석을 볼 수 있습니다.{" "}
          <button onClick={onOpenWizard} className={`underline font-medium ${TOUCH_HEIGHT_MIN}`}>
            지금 설정하기
          </button>
        </div>
      )}
    </div>
  );
}
