import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";
import { buildDiagnosisChips, type DiagnosisChipInput } from "@/utils/diagnosisSummary";

/** 진단 탭 맨 위 요약 칩 — 이탈·시장 종합 판단·쏠림을 한 줄로 보고 탭하면 해당 카드로 스크롤(plans/137 C3).
 * 데이터는 진단 탭이 이미 받는 쿼리를 넘겨받기만 한다(새 요청 없음). */

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export default function DiagnosisSummaryStrip(props: DiagnosisChipInput) {
  const chips = buildDiagnosisChips(props);
  if (chips.length === 0) return null;
  return (
    <nav aria-label="진단 요약" className="flex flex-wrap gap-2 px-1">
      {chips.map((c) => (
        <button
          key={c.key}
          type="button"
          onClick={() => scrollTo(c.target)}
          className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} px-3 rounded-full text-xs font-medium ${c.cls}`}
        >
          {c.label}
        </button>
      ))}
    </nav>
  );
}
