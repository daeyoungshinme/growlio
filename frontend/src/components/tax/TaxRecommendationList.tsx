import { useState } from "react";
import { Lightbulb } from "lucide-react";
import { Link } from "react-router-dom";
import { fmtKrw } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { posKey, type TaxRecommendation } from "@/hooks/useTaxSimulation";
import { assetManagementUrl } from "@/utils/tabUrl";
import SegmentedControl from "@/components/common/SegmentedControl";

type RecMode = "PROFIT_ONLY" | "WITH_LOSS";

interface Props {
  /** 손실 매도 없이 공제 잔여만으로 세금 없이 실현하는 수익 매도 */
  recommendations: TaxRecommendation[];
  /** 손실 종목을 함께 팔아 통산하는 추천(손실 매도가 들어간 경우만, 없으면 빈 배열) */
  lossHarvestRecommendations?: TaxRecommendation[];
  /** 올해 이미 실현한 손익(자동 집계 또는 직접 입력) — 추천이 이 값을 반영했음을 보여준다 */
  alreadyRealized: number;
  /** 손실 매도 없이 세금 0원으로 더 실현할 수 있는 금액 */
  remainingDeduction: number;
}

export function TaxRecommendationList({
  recommendations,
  lossHarvestRecommendations = [],
  alreadyRealized,
  remainingDeduction,
}: Props) {
  const hasLossOption = lossHarvestRecommendations.length > 0;
  const [mode, setMode] = useState<RecMode>(() =>
    recommendations.length === 0 && hasLossOption ? "WITH_LOSS" : "PROFIT_ONLY",
  );
  const activeMode: RecMode = hasLossOption ? mode : "PROFIT_ONLY";
  const rows = activeMode === "WITH_LOSS" ? lossHarvestRecommendations : recommendations;

  return (
    <div className="rounded-xl border border-amber-200 dark:border-amber-800/50 bg-amber-50 dark:bg-amber-900/20 p-4 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Lightbulb size={13} className="text-amber-500 shrink-0" />
          <span className="text-xs font-semibold text-amber-700 dark:text-amber-400">
            절세 추천 — 세금 없이 실현 가능한 매도
          </span>
        </div>
        {hasLossOption && (
          <SegmentedControl
            ariaLabel="절세 추천 방식"
            options={[
              { value: "PROFIT_ONLY", label: "수익만 매도" },
              { value: "WITH_LOSS", label: "손실 통산 포함" },
            ]}
            value={activeMode}
            onChange={setMode}
          />
        )}
      </div>
      <p className="text-xs text-amber-700 dark:text-amber-400" data-testid="rec-basis">
        올해 실현 {fmtKrw(alreadyRealized)} 반영 · 공제 잔여 {fmtKrw(remainingDeduction)}
        {activeMode === "WITH_LOSS"
          ? " — 아래 손실 종목을 함께 매도해야(손익 통산) 세금이 0원이에요"
          : " — 손실 종목은 그대로 두고 공제 잔여만 써요"}
      </p>
      {rows.length === 0 ? (
        <p className="text-xs text-gray-600 dark:text-gray-300" data-testid="rec-profit-only-empty">
          공제 잔여로는 손실 매도 없이 세금 없이 실현할 수 있는 매도가 없어요(1주 수익이 잔여보다
          커요). "손실 통산 포함"을 보세요.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {rows.map(({ pos, kind, label, realizedKrw, taxSaved }) => (
            <li
              key={`rec-${kind}-${posKey(pos)}`}
              className="flex flex-wrap items-start justify-between gap-y-1 text-xs"
            >
              <span className="flex-1 min-w-0 text-gray-700 dark:text-gray-300">
                <span className="font-medium">{pos.ticker}</span>{" "}
                <span className="text-gray-500 dark:text-gray-400">{label}</span>
                {" → "}
                {kind === "LOSS" ? "손실 " : "수익 "}
                <span className={pnlColor(realizedKrw)}>{fmtKrw(realizedKrw)}</span> 실현
                <Link
                  to={assetManagementUrl("증권계좌")}
                  className="ml-1.5 text-blue-600 dark:text-blue-400 hover:underline"
                >
                  {pos.account_name}에서 매도 →
                </Link>
              </span>
              {kind === "LOSS" ? (
                <span className="text-blue-600 dark:text-blue-400 font-medium ml-2 shrink-0">
                  손익 통산용
                </span>
              ) : (
                <span className="text-emerald-600 dark:text-emerald-400 font-medium ml-2 shrink-0">
                  세금 절감 {fmtKrw(taxSaved)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-amber-600 dark:text-amber-500 mt-1">
        * 수익 종목 테이블에서 매도 수량을 직접 입력하면 자세한 시뮬레이션을 확인할 수 있습니다.
      </p>
    </div>
  );
}
