import { Trash2, Unlink, X } from "lucide-react";
import type { IndexGroupSuggestion, PortfolioGroupMember, PortfolioItem } from "@/api/portfolios";
import { INPUT_SM } from "@/constants/inputStyles";
import { isOverseasMarket, marketLabel } from "@/constants/markets";
import {
  TOUCH_TARGET_COMPACT_MOBILE_ONLY,
  TOUCH_TARGET_MIN_MOBILE_ONLY,
} from "@/constants/uiSizes";
import {
  isLeveraged,
  outOfScopeAccounts,
  removeGroupMember,
  scopedMemberLabel,
  setGroupDomesticAlt,
  setGroupPrimary,
  ungroupItem,
} from "@/utils/portfolioGroups";

interface Props {
  item: PortfolioItem;
  idx: number;
  /** 같은 지수 키의 제안 — 있으면 대표·국내 대체 종목을 후보에서 고를 수 있다 */
  suggestion?: IndexGroupSuggestion;
  onChange: (idx: number, item: PortfolioItem) => void;
  onRemove: (idx: number) => void;
}

const keyOf = (m: { ticker: string; market: string }) => `${m.ticker}|${m.market}`;

function uniqueCandidates(list: PortfolioGroupMember[]): PortfolioGroupMember[] {
  const seen = new Set<string>();
  return list.filter((m) => !seen.has(keyOf(m)) && !!seen.add(keyOf(m)));
}

// 지수 그룹 항목(plans/74) 한 행 — 이탈은 묶인 종목 합계로, 매수는 대표 종목(ISA·연금 계좌는 국내 대체 종목)으로
export default function PortfolioGroupItemRow({
  item,
  idx,
  suggestion,
  onChange,
  onRemove,
}: Props) {
  const group = item.group!;
  const primaryOptions = uniqueCandidates([
    item,
    ...group.members.filter((m) => !isLeveraged(m)),
    ...(suggestion?.primary_candidates ?? []),
  ]);
  const altOptions = uniqueCandidates([
    ...(group.domestic_alt ? [group.domestic_alt] : []),
    ...group.members.filter((m) => !isOverseasMarket(m.market) && !isLeveraged(m)),
    ...(suggestion?.domestic_alt_candidates ?? []),
  ]);
  const hasLeveraged = group.members.some(isLeveraged);
  const outside = outOfScopeAccounts(suggestion);
  const outsideNames = [item, ...group.members]
    .filter((m) => outside.has(keyOf(m)))
    .map((m) => m.name || m.ticker);
  const byKey = new Map([...primaryOptions, ...altOptions].map((m) => [keyOf(m), m]));

  return (
    <div className="border border-indigo-200 dark:border-indigo-800/60 bg-indigo-50/40 dark:bg-indigo-950/20 rounded-lg px-3 py-2.5 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-indigo-700 bg-indigo-100 dark:text-indigo-300 dark:bg-indigo-900/50 px-2 py-0.5 rounded shrink-0">
          지수
        </span>
        <span className="flex-1 min-w-0 text-sm font-semibold text-gray-800 dark:text-gray-50 truncate">
          {group.label || group.key}
        </span>
        <input
          type="number"
          inputMode="decimal"
          min={0}
          max={100}
          step={0.1}
          aria-label={`${group.label} 목표 비중`}
          className="w-20 sm:w-24 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm text-right focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="%"
          value={item.weight || ""}
          onChange={(e) => onChange(idx, { ...item, weight: parseFloat(e.target.value) || 0 })}
        />
        <button
          onClick={() => onRemove(idx)}
          aria-label="항목 삭제"
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-1.5 text-gray-400 dark:text-gray-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors`}
        >
          <Trash2 size={15} />
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <label className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
          <span>대표 매수 종목</span>
          <select
            className={INPUT_SM}
            value={keyOf(item)}
            onChange={(e) => {
              const next = byKey.get(e.target.value);
              if (next) onChange(idx, setGroupPrimary(item, next));
            }}
          >
            {primaryOptions.map((m) => (
              <option key={keyOf(m)} value={keyOf(m)}>
                {m.name || m.ticker} ({m.ticker} · {marketLabel(m.market)})
              </option>
            ))}
          </select>
        </label>
        {isOverseasMarket(item.market) && (
          <label className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
            <span>ISA·연금 계좌 대체 매수</span>
            <select
              className={INPUT_SM}
              value={group.domestic_alt ? keyOf(group.domestic_alt) : ""}
              onChange={(e) =>
                onChange(idx, setGroupDomesticAlt(item, byKey.get(e.target.value) ?? null))
              }
            >
              <option value="">없음 (해외 종목 매수 건너뜀)</option>
              {altOptions.map((m) => (
                <option key={keyOf(m)} value={keyOf(m)}>
                  {m.name || m.ticker} ({m.ticker})
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-gray-500 dark:text-gray-400">함께 합산:</span>
        {group.members.length === 0 && (
          <span className="text-xs text-gray-400 dark:text-gray-500">없음</span>
        )}
        {group.members.map((m) => (
          <span
            key={keyOf(m)}
            className={`inline-flex items-center gap-1 text-xs rounded-full pl-2 pr-1 py-0.5 border ${
              outside.has(keyOf(m))
                ? "bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-900/20 dark:border-amber-700/50 dark:text-amber-300"
                : "bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300"
            }`}
          >
            {scopedMemberLabel(m, outside.get(keyOf(m)))}
            <button
              type="button"
              aria-label={`${m.name || m.ticker} 그룹에서 빼기`}
              onClick={() => onChange(idx, removeGroupMember(item, m))}
              className="p-0.5 text-gray-400 hover:text-red-600 rounded-full"
            >
              <X size={11} />
            </button>
          </span>
        ))}
        <button
          type="button"
          onClick={() => onChange(idx, ungroupItem(item))}
          className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} ml-auto gap-1 text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200`}
        >
          <Unlink size={12} /> 묶음 해제
        </button>
      </div>
      {outsideNames.length > 0 && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          {outsideNames.join(", ")}은(는) 분석 대상 계좌 밖에 있어 지금은 0원으로 합산돼요. 보유
          계좌를 아래 분석 대상 계좌에 추가하세요.
        </p>
      )}
      {hasLeveraged && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          레버리지 종목은 배수만큼 노출로 계산해요(예: QLD 100만원 = 나스닥 100 200만원). 매수는 1배
          대표 종목으로만 해요.
        </p>
      )}
    </div>
  );
}
