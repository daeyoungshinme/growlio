import type { AssetAccount } from "@/api/assets";
import { INPUT_SM } from "@/constants/inputStyles";
import NoTradableAccountNotice from "./NoTradableAccountNotice";

interface Props {
  accounts: AssetAccount[];
  value: string;
  onChange: (accountId: string) => void;
}

/** AUTO 실행 계좌 선택 — 없으면 안내, 1개면 자동 선택 표시(값은 모달 effect가 채움), 2개 이상이면 선택. */
export default function AutoExecutionAccountPicker({ accounts, value, onChange }: Props) {
  if (accounts.length === 0) return <NoTradableAccountNotice />;
  if (accounts.length === 1) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-300">
        <span>{accounts[0].name}</span>
        <span className="text-xs text-gray-400 dark:text-gray-500">(자동 선택)</span>
      </div>
    );
  }
  return (
    <select
      className={`w-full ${INPUT_SM}`}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">계좌 선택</option>
      {accounts.map((a) => (
        <option key={a.id} value={a.id}>
          {a.name}
        </option>
      ))}
    </select>
  );
}
