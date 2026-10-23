import { ChartColumn } from "lucide-react";
import { RebalancingAnalysis } from "@/api/rebalancing";
import { CagrCard } from "./RebalancingCells";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import { useCollapsible } from "@/hooks/useCollapsible";

function hhiLabel(hhi: number) {
  if (hhi < 1000) return { text: "분산형", cls: "text-green-600 dark:text-green-400" };
  if (hhi < 2500) return { text: "보통", cls: "text-yellow-600 dark:text-yellow-400" };
  return { text: "집중형", cls: "text-red-600 dark:text-red-400" };
}

interface Props {
  analysis: RebalancingAnalysis;
}

// 상세 지표 (집중도 · CAGR) — 접기/펼치기
export default function RebalancingDetailMetrics({ analysis }: Props) {
  const [isOpen, toggleOpen] = useCollapsible(false);

  const hasCagrData =
    analysis.target_weighted_cagr_10y_pct != null || analysis.current_weighted_cagr_10y_pct != null;

  const currentHHI = analysis.items.reduce((s, i) => s + i.current_weight_pct ** 2, 0);
  const targetHHI = analysis.items
    .filter((i) => i.target_weight_pct > 0)
    .reduce((s, i) => s + i.target_weight_pct ** 2, 0);

  const curLabel = hhiLabel(currentHHI);
  const tgtLabel = hhiLabel(targetHHI);

  return (
    <CollapsibleCard
      icon={ChartColumn}
      title="상세 지표"
      isOpen={isOpen}
      onToggle={toggleOpen}
      cardClassName="border border-gray-200 dark:border-gray-700/50 rounded-xl p-4"
    >
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-gray-100 dark:bg-gray-700 rounded-xl p-3 text-center">
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">현재 종목 집중도</div>
            <div className={`text-sm font-semibold ${curLabel.cls}`}>{curLabel.text}</div>
            <div className="text-xs text-gray-500 dark:text-gray-500 mt-0.5">
              지수 {currentHHI.toFixed(0)}
            </div>
          </div>
          <div className="bg-gray-100 dark:bg-gray-700 rounded-xl p-3 text-center">
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">목표 종목 집중도</div>
            <div className={`text-sm font-semibold ${tgtLabel.cls}`}>{tgtLabel.text}</div>
            <div className="text-xs text-gray-500 dark:text-gray-500 mt-0.5">
              지수 {targetHHI.toFixed(0)}
            </div>
          </div>
        </div>
        {/* title 툴팁은 터치에서 안 보여 설명을 화면에 적는다 (docs/plans/67 P1-10) */}
        <p className="text-xs text-gray-500 dark:text-gray-400">
          집중도 지수(HHI)는 낮을수록 종목이 고르게 나뉜 상태예요.
        </p>
        {hasCagrData && (
          <div className="grid grid-cols-2 gap-3">
            <CagrCard label="현재 포트폴리오 CAGR" cagr={analysis.current_weighted_cagr_10y_pct} />
            <CagrCard label="목표 포트폴리오 CAGR" cagr={analysis.target_weighted_cagr_10y_pct} />
          </div>
        )}
      </div>
    </CollapsibleCard>
  );
}
