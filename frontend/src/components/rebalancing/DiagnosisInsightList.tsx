import { useState } from "react";
import { ChevronDown, Receipt, ShieldAlert, Target, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import type { DiagnosisContext } from "@/api/rebalancing";
import { buildDiagnosisNotes, type DiagnosisNoteIcon } from "@/utils/diagnosisInsights";
import { fmtKrw } from "@/utils/format";

const NOTE_ICONS: Record<DiagnosisNoteIcon, React.ReactNode> = {
  market: <TrendingUp size={13} className="text-blue-400 shrink-0" />,
  risk: <ShieldAlert size={13} className="text-amber-400 shrink-0" />,
  tax: <Receipt size={13} className="text-gray-400 shrink-0" />,
  goal: <Target size={13} className="text-purple-400 shrink-0" />,
};

interface Props {
  context: DiagnosisContext | null | undefined;
  targetCagrPct?: number | null;
  targetDividendKrw?: number | null;
}

/** 리밸런싱 진단 카드에 시장상황·리스크·세금영향·목표비교 부가 인사이트를 표시한다. 신호가 없으면 조용히 아무것도 렌더링하지 않는다. */
export default function DiagnosisInsightList({ context, targetCagrPct, targetDividendKrw }: Props) {
  const [showDetail, setShowDetail] = useState(false);

  if (!context) return null;
  const notes = buildDiagnosisNotes(context, targetCagrPct, targetDividendKrw);
  if (notes.length === 0) return null;

  const detailItems = context.tax_detail_items;

  return (
    <div className="mt-3 space-y-1.5 border-t border-gray-700/50 pt-3">
      {notes.map((note, i) => (
        <div key={`${note.icon}-${i}`} className="flex items-start gap-1.5 text-xs text-gray-300">
          {NOTE_ICONS[note.icon]}
          <span className="flex-1">{note.text}</span>
          {note.icon === "goal" && (
            <Link to="/invest-plan" className="text-blue-400 hover:underline shrink-0">
              목표 수정하기
            </Link>
          )}
        </div>
      ))}

      {detailItems.length > 0 && (
        <div>
          <button
            onClick={() => setShowDetail((v) => !v)}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
            aria-expanded={showDetail}
            aria-label="세금 영향 상세 보기"
          >
            자세히
            <ChevronDown
              size={12}
              className={`transition-transform duration-200 ${showDetail ? "rotate-180" : ""}`}
            />
          </button>
          {showDetail && (
            <ul className="mt-1.5 space-y-1">
              {detailItems.map((item) => (
                <li
                  key={`${item.ticker}-${item.market}`}
                  className="flex justify-between text-xs text-gray-400"
                >
                  <span>
                    {item.name} ({item.ticker})
                  </span>
                  <span>
                    {item.excluded_reason ?? (
                      <>
                        {item.estimated_realized_gain_krw >= 0 ? "+" : ""}
                        {fmtKrw(item.estimated_realized_gain_krw)}
                      </>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
