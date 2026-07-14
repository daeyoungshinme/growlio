import { useState } from "react";
import { ChevronDown, Receipt, ShieldAlert, TrendingUp } from "lucide-react";
import type { DiagnosisContext } from "@/api/rebalancing";
import { buildDiagnosisNotes, type DiagnosisNoteIcon } from "@/utils/diagnosisInsights";
import { fmtKrw } from "@/utils/format";

const NOTE_ICONS: Record<DiagnosisNoteIcon, React.ReactNode> = {
  market: <TrendingUp size={13} className="text-blue-400 shrink-0" />,
  risk: <ShieldAlert size={13} className="text-amber-400 shrink-0" />,
  tax: <Receipt size={13} className="text-gray-400 shrink-0" />,
};

interface Props {
  context: DiagnosisContext | null | undefined;
}

/** 리밸런싱 진단 카드에 시장상황·리스크·세금영향 부가 인사이트를 표시한다. 신호가 없으면 조용히 아무것도 렌더링하지 않는다. */
export default function DiagnosisInsightList({ context }: Props) {
  const [showDetail, setShowDetail] = useState(false);

  if (!context) return null;
  const notes = buildDiagnosisNotes(context);
  if (notes.length === 0) return null;

  const detailItems = context.tax_detail_items;

  return (
    <div className="mt-3 space-y-1.5 border-t border-gray-700/50 pt-3">
      {notes.map((note, i) => (
        <div key={`${note.icon}-${i}`} className="flex items-start gap-1.5 text-xs text-gray-300">
          {NOTE_ICONS[note.icon]}
          <span className="flex-1">{note.text}</span>
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
                  <span className="flex items-center gap-1">
                    {item.name} ({item.ticker})
                    {item.is_tax_deferred && (
                      <span className="px-1 py-px border border-purple-700 text-purple-400 rounded-full text-xs leading-tight">
                        과세이연
                      </span>
                    )}
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
