import { AssetAccount } from "@/api/assets";

interface Props {
  accounts: AssetAccount[];
  selectedAccountIds: Set<string>;
  isAllSelected: boolean;
  onToggleAccount: (id: string) => void;
  onSelectAll: () => void;
}

export default function PortfolioAccountSelector({
  accounts,
  selectedAccountIds,
  isAllSelected,
  onToggleAccount,
  onSelectAll,
}: Props) {
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
      <div className="flex flex-wrap gap-x-3 sm:gap-x-5 gap-y-2 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        {accounts.map((acc) => (
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
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
        {isAllSelected
          ? "모든 주식 계좌가 리밸런싱 분석에 포함됩니다."
          : `${selectedAccountIds.size}개 계좌만 분석에 포함됩니다.`}{" "}
        동일 계좌를 여러 포트폴리오에 동시에 포함할 수 있습니다.
      </p>
    </div>
  );
}
