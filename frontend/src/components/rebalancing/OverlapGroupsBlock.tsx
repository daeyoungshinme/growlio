import { useState } from "react";
import type { OverlapGroup } from "@/api/rebalancing";
import CollapsibleSection from "@/components/common/CollapsibleSection";
import { TOUCH_TARGET_ROW } from "@/constants/uiSizes";
import { fmtKrwPrice } from "@/utils/format";
import {
  annualCostGapPer10M,
  formatTerPct,
  isCheapest,
  isMixedListing,
  itemKey,
  reasonLabel,
} from "@/utils/etfOverlap";

interface Props {
  groups: OverlapGroup[];
  /** 추천 비중(ticker:market → %) — 그룹 멤버 옆에 함께 보여준다. */
  weightByKey: Map<string, number>;
}

/** 추천 결과에 포함된 종목 중 보유 종목·다른 후보와 같은 지수를 추종하거나 사실상 같이 움직이는
 * 묶음을 보여준다 — 정보 제공 전용(교체 권유 아님). 기본 접힘, 그룹이 없으면 렌더하지 않는다. */
export default function OverlapGroupsBlock({ groups, weightByKey }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  if (groups.length === 0) return null;

  const heldCount = groups.filter((g) => g.members.some((m) => m.held)).length;
  const hint =
    heldCount > 0
      ? `보유 종목과 겹치는 묶음 ${heldCount}개 포함`
      : "같은 지수를 추종하는 후보가 함께 추천됐어요";

  return (
    <CollapsibleSection
      isOpen={isOpen}
      onToggle={() => setIsOpen((v) => !v)}
      label={`중복 투자 점검 · ${groups.length}개 묶음`}
      collapsedHint={hint}
      buttonClassName={`${TOUCH_TARGET_ROW} w-full gap-1 text-xs text-amber-600 dark:text-amber-500 font-medium rounded-lg transition-colors`}
    >
      <ul className="space-y-2">
        {groups.map((g) => (
          <li
            key={g.members.map((m) => itemKey(m.ticker, m.market)).join("|")}
            className="rounded-lg border border-amber-200 dark:border-amber-800/50 bg-amber-50/60 dark:bg-amber-950/20 p-2.5 space-y-1.5"
          >
            <p className="text-xs font-medium text-amber-700 dark:text-amber-400">
              {reasonLabel(g)}
            </p>
            <ul className="space-y-1">
              {g.members.map((m) => {
                const weight = weightByKey.get(itemKey(m.ticker, m.market));
                return (
                  <li
                    key={itemKey(m.ticker, m.market)}
                    className="flex items-start justify-between gap-2 text-xs"
                  >
                    <span className="text-gray-700 dark:text-gray-300 min-w-0">
                      {m.name}
                      <span className="text-gray-400 dark:text-gray-500"> ({m.ticker})</span>
                      {m.held && (
                        <span className="ml-1 text-gray-500 dark:text-gray-400">· 보유 중</span>
                      )}
                      {weight != null && weight > 0 && (
                        <span className="ml-1 text-teal-600 dark:text-teal-400">
                          · 추천 {weight.toFixed(1)}%
                        </span>
                      )}
                    </span>
                    <span
                      className={`shrink-0 ${
                        isCheapest(g, m)
                          ? "font-medium text-teal-600 dark:text-teal-400"
                          : "text-gray-500 dark:text-gray-400"
                      }`}
                    >
                      {m.ter_pct != null ? `보수 ${formatTerPct(m.ter_pct)}` : "보수 확인 불가"}
                      {isCheapest(g, m) && " · 최저"}
                    </span>
                  </li>
                );
              })}
            </ul>
            {g.ter_gap_pct != null && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                보수 차이 최대 {formatTerPct(g.ter_gap_pct)}p — 1,000만원 보유 시 연 약{" "}
                {fmtKrwPrice(annualCostGapPer10M(g.ter_gap_pct))}
                {isMixedListing(g) &&
                  " (국내·해외 상장이 섞여 있어 세금·환전 비용은 별도로 비교해야 해요)"}
              </p>
            )}
          </li>
        ))}
      </ul>
      <p className="text-xs text-gray-400 dark:text-gray-500 pt-2">
        같은 지수의 ETF를 여러 개 사면 분산 효과 없이 관리만 늘어나요. 이미 보유한 종목을 바꾸려면
        매도 시 세금·거래비용이 생길 수 있으니 신규 매수분부터 조정하는 것을 고려해보세요.
      </p>
    </CollapsibleSection>
  );
}
