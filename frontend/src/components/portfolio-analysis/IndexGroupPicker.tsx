import { Loader2 } from "lucide-react";
import type { IndexGroupSuggestion, IndexGroupSuggestionResponse } from "@/api/portfolios";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";
import { isLeveraged, outOfScopeAccounts, scopedMemberLabel } from "@/utils/portfolioGroups";

interface Props {
  data?: IndexGroupSuggestionResponse;
  isLoading: boolean;
  isError: boolean;
  /** 이미 그룹으로 묶인 지수 키 */
  appliedKeys: Set<string>;
  onApply: (suggestion: IndexGroupSuggestion) => void;
}

// "지수로 묶기" 제안 목록(plans/74) — 같은 지수를 추종하는 보유 ETF 묶음을 고르면 그룹 항목 하나로 합쳐진다
export default function IndexGroupPicker({
  data,
  isLoading,
  isError,
  appliedKeys,
  onApply,
}: Props) {
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 py-2">
        <Loader2 size={12} className="animate-spin" /> 보유 종목의 추종 지수를 확인하는 중…
      </div>
    );
  }
  if (isError) {
    return (
      <p className="text-xs text-red-600 dark:text-red-400 py-2">지수 묶음을 불러오지 못했어요.</p>
    );
  }
  const groups = data?.groups ?? [];
  if (!groups.length) {
    return (
      <p className="text-xs text-gray-500 dark:text-gray-400 py-2">
        묶을 수 있는 지수 ETF 보유 종목이 없어요. 개별주·레버리지·테마 ETF는 지수로 묶지 않아요.
      </p>
    );
  }
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-gray-500 dark:text-gray-400">
        같은 지수를 추종하는 종목을 한 항목으로 묶어요. 비중 이탈은 묶인 종목 합계로 판단하고,
        매수는 대표 종목으로 해요.
      </p>
      {!data?.profiles_complete && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          일부 종목의 ETF 정보를 불러오지 못해 목록이 빠졌을 수 있어요.
        </p>
      )}
      {groups.map((g) => {
        const applied = appliedKeys.has(g.key);
        const outside = outOfScopeAccounts(g);
        const key = (m: { ticker: string; market: string }) => `${m.ticker}|${m.market}`;
        const outsideNames = g.members
          .filter((m) => outside.has(key(m)))
          .map((m) => m.name || m.ticker);
        return (
          <div
            key={g.key}
            className="flex items-center gap-2 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-800 dark:text-gray-50">
                {g.label}{" "}
                <span className="text-xs font-normal text-gray-500 dark:text-gray-400">
                  전체 계좌 주식의 {g.pct_of_stock.toFixed(1)}%
                </span>
              </p>
              {/* 한 줄 말줄임이면 뒤쪽 멤버(QLD 등)가 잘려 보이지 않았다 — 줄바꿈 칩으로 전부 보여준다 */}
              <ul className="flex flex-wrap gap-1 mt-1">
                {g.members.map((m) => {
                  const isOutside = outside.has(key(m));
                  return (
                    <li
                      key={key(m)}
                      className={`text-xs rounded-full px-2 py-0.5 border ${
                        isOutside
                          ? "bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-900/20 dark:border-amber-700/50 dark:text-amber-300"
                          : "bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300"
                      }`}
                    >
                      {scopedMemberLabel(m, outside.get(key(m)))}
                      {key(m) === key(g.primary) && " · 대표"}
                    </li>
                  );
                })}
              </ul>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                대표 매수 {g.primary.name || g.primary.ticker}
                {g.domestic_alt
                  ? ` · ISA·연금 ${g.domestic_alt.name || g.domestic_alt.ticker}`
                  : ""}
              </p>
              {g.members.some(isLeveraged) && (
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  레버리지 종목은 배수만큼 노출로 합산해요.
                </p>
              )}
              {outsideNames.length > 0 && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  {outsideNames.join(", ")}은(는) 분석 대상 계좌 밖에 있어요 — 분석 대상 계좌에
                  추가해야 합산돼요
                </p>
              )}
            </div>
            <button
              type="button"
              disabled={applied}
              onClick={() => onApply(g)}
              className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} shrink-0 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 px-2 py-1 rounded-lg disabled:opacity-40`}
            >
              {applied ? "묶음" : "묶기"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
