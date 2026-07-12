import { useMemo } from "react";
import { AssetAccount, INVESTMENT_HORIZON_LABELS, InvestmentHorizon } from "@/api/assets";

interface Props {
  accounts: AssetAccount[];
  selectedAccountIds: Set<string>;
  isAllSelected: boolean;
  onToggleAccount: (id: string) => void;
  onSelectAll: () => void;
}

type HorizonGroupKey = InvestmentHorizon | "UNSET";

const HORIZON_ORDER: HorizonGroupKey[] = ["SHORT_TERM", "MID_TERM", "LONG_TERM", "UNSET"];

export default function PortfolioAccountSelector({
  accounts,
  selectedAccountIds,
  isAllSelected,
  onToggleAccount,
  onSelectAll,
}: Props) {
  // 계좌에 지정된 투자기간(단기/중기/장기) 태그별로 묶어서 표시 — 계좌군 단위로 포트폴리오를
  // 구성하려는 사용자가 한눈에 그룹을 파악할 수 있게 한다. 태그가 없으면 그룹 헤더 없이 평탄하게 표시.
  const groups = useMemo(() => {
    const map = new Map<HorizonGroupKey, AssetAccount[]>();
    for (const acc of accounts) {
      const key: HorizonGroupKey = acc.investment_horizon ?? "UNSET";
      const list = map.get(key);
      if (list) list.push(acc);
      else map.set(key, [acc]);
    }
    return HORIZON_ORDER.filter((k) => map.has(k)).map((key) => ({ key, accounts: map.get(key)! }));
  }, [accounts]);

  const showGroupHeaders = groups.length > 1;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          분석 대상 계좌
        </label>
        {!isAllSelected && (
          <button
            type="button"
            onClick={onSelectAll}
            className="text-xs text-blue-600 hover:underline"
          >
            전체 선택
          </button>
        )}
      </div>
      <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 space-y-3">
        {groups.map((group) => (
          <div key={group.key}>
            {showGroupHeaders && (
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
                {group.key === "UNSET" ? "기간 미지정" : INVESTMENT_HORIZON_LABELS[group.key]}
              </p>
            )}
            <div className="flex flex-wrap gap-x-3 sm:gap-x-5 gap-y-2">
              {group.accounts.map((acc) => (
                <label key={acc.id} className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedAccountIds.has(acc.id)}
                    onChange={() => onToggleAccount(acc.id)}
                    className="rounded text-blue-600"
                  />
                  <span className="text-sm text-gray-700 dark:text-gray-300">{acc.name}</span>
                  {acc.is_mock_mode && (
                    <span className="text-xs text-gray-400 dark:text-gray-500">(모의)</span>
                  )}
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
        {isAllSelected
          ? "모든 주식 계좌가 리밸런싱 분석에 포함됩니다."
          : `${selectedAccountIds.size}개 계좌만 분석에 포함됩니다.`}{" "}
        동일 계좌를 여러 포트폴리오에 동시에 포함할 수 있습니다.
      </p>
    </div>
  );
}
