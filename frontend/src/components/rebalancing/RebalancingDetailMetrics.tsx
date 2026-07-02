import { useState } from "react";
import { RebalancingAnalysis } from "@/api/rebalancing";
import { CagrCard } from "./RebalancingCells";

function hhiLabel(hhi: number) {
  if (hhi < 1000) return { text: "분산형", cls: "text-green-400" };
  if (hhi < 2500) return { text: "보통", cls: "text-yellow-400" };
  return { text: "집중형", cls: "text-red-400" };
}

interface Props {
  analysis: RebalancingAnalysis;
}

// 상세 지표 (집중도 · CAGR) — 접기/펼치기
export default function RebalancingDetailMetrics({ analysis }: Props) {
  const [showDetails, setShowDetails] = useState(false);

  const hasCagrData =
    analysis.target_weighted_cagr_10y_pct != null || analysis.current_weighted_cagr_10y_pct != null;

  const currentHHI = analysis.items.reduce((s, i) => s + i.current_weight_pct ** 2, 0);
  const targetHHI = analysis.items
    .filter((i) => i.target_weight_pct > 0)
    .reduce((s, i) => s + i.target_weight_pct ** 2, 0);

  const curLabel = hhiLabel(currentHHI);
  const tgtLabel = hhiLabel(targetHHI);

  return (
    <div className="border border-gray-700/50 rounded-xl overflow-hidden">
      <button
        onClick={() => setShowDetails((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-xs text-gray-400 hover:bg-gray-700/40 transition-colors"
      >
        <span className="font-medium">상세 지표</span>
        <span>{showDetails ? "▲" : "▼"}</span>
      </button>
      {showDetails && (
        <div className="px-4 pb-4 pt-2 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div
              className="bg-gray-700 rounded-xl p-3 text-center"
              title="집중도 지수(HHI): 낮을수록 종목이 고르게 분산된 포트폴리오입니다"
            >
              <div className="text-xs text-gray-400 mb-1">현재 집중도</div>
              <div className={`text-sm font-semibold ${curLabel.cls}`}>{curLabel.text}</div>
              <div className="text-xs text-gray-500 mt-0.5">HHI {currentHHI.toFixed(0)}</div>
            </div>
            <div className="bg-gray-700 rounded-xl p-3 text-center" title="리밸런싱 후 목표 집중도">
              <div className="text-xs text-gray-400 mb-1">목표 집중도</div>
              <div className={`text-sm font-semibold ${tgtLabel.cls}`}>{tgtLabel.text}</div>
              <div className="text-xs text-gray-500 mt-0.5">HHI {targetHHI.toFixed(0)}</div>
            </div>
          </div>
          {hasCagrData && (
            <div className="grid grid-cols-2 gap-3">
              <CagrCard label="현재 포트폴리오 CAGR" cagr={analysis.current_weighted_cagr_10y_pct} />
              <CagrCard label="목표 포트폴리오 CAGR" cagr={analysis.target_weighted_cagr_10y_pct} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
