import { useState } from "react";
import { fmtKrw } from "@/utils/format";
import type { IndexExposure, IndexExposureGroup } from "@/types";
import SegmentedControl from "./SegmentedControl";
import WeightBarRow, { ListingBadge } from "./WeightBarRow";

type Basis = "stock" | "etf";

const BASIS_OPTIONS = [
  { value: "stock", label: "주식 전체" },
  { value: "etf", label: "ETF만" },
] as const;

const KIND_HINT: Partial<Record<IndexExposureGroup["kind"], string>> = {
  LEVERAGED: "배수 노출은 반영하지 않은 평가금액 기준",
  OTHER_ETF: "추종 지수를 자동으로 판별하지 못한 ETF",
};

function groupPct(group: IndexExposureGroup, basis: Basis): number {
  return basis === "etf" ? (group.pct_of_etf ?? 0) : group.pct_of_stock;
}

function listingSplit(group: IndexExposureGroup): string | null {
  if (group.value_krw <= 0 || group.domestic_krw <= 0 || group.overseas_krw <= 0) return null;
  const domesticPct = (group.domestic_krw / group.value_krw) * 100;
  return `국내상장 ${domesticPct.toFixed(0)}% · 해외상장 ${(100 - domesticPct).toFixed(0)}%`;
}

function GroupRow({ group, basis }: { group: IndexExposureGroup; basis: Basis }) {
  return (
    <WeightBarRow
      label={group.label}
      pct={groupPct(group, basis)}
      badges={
        group.has_hedged && (
          <span className="shrink-0 text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">
            (H) 포함
          </span>
        )
      }
      subLeft={listingSplit(group) ?? KIND_HINT[group.kind] ?? `${group.members.length}종목`}
      subRight={fmtKrw(group.value_krw)}
    >
      {group.members.length > 0 && (
        <ul className="mt-1 ml-1 space-y-1.5 border-l-2 border-gray-100 dark:border-gray-700 pl-3">
          {group.members.map((m) => (
            <li
              key={`${m.ticker}-${m.market}`}
              className="flex items-center justify-between gap-2 text-xs"
            >
              <span className="min-w-0 flex items-center gap-1.5">
                <ListingBadge market={m.market} />
                <span className="truncate text-gray-700 dark:text-gray-300">{m.name}</span>
                <span className="shrink-0 text-gray-400 dark:text-gray-500">{m.ticker}</span>
              </span>
              <span className="shrink-0 text-gray-500 dark:text-gray-400 tabular-nums">
                {fmtKrw(m.value_krw)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </WeightBarRow>
  );
}

/** 추종 지수별 비중 — SPY와 TIGER 미국S&P500처럼 같은 지수를 추종하는 국내·해외 ETF를 합산해 보여준다. */
export default function IndexAllocationView({ data }: { data: IndexExposure }) {
  const [basis, setBasis] = useState<Basis>("stock");

  if (data.total_etf_krw <= 0) {
    return (
      <p className="py-4 text-center text-sm text-gray-500 dark:text-gray-400">
        보유 중인 ETF가 없어요.
      </p>
    );
  }

  const groups = data.groups.filter((g) => basis === "stock" || g.kind !== "STOCK");

  return (
    <div>
      <SegmentedControl
        options={BASIS_OPTIONS}
        value={basis}
        onChange={setBasis}
        ariaLabel="지수 비중 기준"
      />
      <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
        같은 지수를 추종하는 국내·해외 ETF를 합산했어요. 환헤지(H)·합성 상품은 원 지수에 포함돼요.
        기준 금액{" "}
        <span className="tabular-nums">
          {fmtKrw(basis === "etf" ? data.total_etf_krw : data.total_stock_krw)}
        </span>
      </p>
      {!data.profiles_complete && (
        <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
          일부 종목의 ETF 정보를 불러오지 못해 분류가 정확하지 않을 수 있어요.
        </p>
      )}
      <ul className="mt-1 divide-y divide-gray-100 dark:divide-gray-700">
        {groups.map((g) => (
          <GroupRow key={g.key} group={g} basis={basis} />
        ))}
      </ul>
    </div>
  );
}
