import { useState } from "react";
import { X } from "lucide-react";
import type { AssetAccount, AssetAccountCreate } from "../../api/assets";
import { useExchangeRate } from "../../hooks/useExchangeRate";
import { fmtKrw } from "../../utils/format";

interface Props {
  initialAccount?: AssetAccount;
  onClose: () => void;
  onSubmit: (data: AssetAccountCreate) => void;
  isLoading: boolean;
}

export default function BankAccountModal({ initialAccount, onClose, onSubmit, isLoading }: Props) {
  const isEdit = !!initialAccount;

  const [form, setForm] = useState({
    name: initialAccount?.name ?? "",
    institution: initialAccount?.institution ?? "",
    asset_type: initialAccount?.asset_type ?? "BANK_ACCOUNT",
    notes: initialAccount?.notes ?? "",
  });

  const [depositKrw, setDepositKrw] = useState<number | undefined>(
    initialAccount?.deposit_krw != null
      ? initialAccount.deposit_krw
      : initialAccount?.manual_amount != null
        ? initialAccount.manual_amount
        : undefined
  );
  const [depositUsd, setDepositUsd] = useState<number | undefined>(
    initialAccount?.deposit_usd != null && initialAccount.deposit_usd > 0
      ? initialAccount.deposit_usd
      : undefined
  );

  const usdRate = useExchangeRate();
  const usdAsKrw = depositUsd && usdRate ? Math.round(depositUsd * usdRate) : 0;
  const totalKrw = (depositKrw ?? 0) + usdAsKrw;

  const usdPending = (depositUsd ?? 0) > 0 && usdRate == null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      name: form.name,
      institution: form.institution || undefined,
      asset_type: form.asset_type,
      data_source: "MANUAL",
      deposit_krw: depositKrw ?? 0,
      deposit_usd: depositUsd ?? 0,
      manual_amount: totalKrw > 0 ? totalKrw : undefined,
      notes: form.notes || undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 w-full max-w-md p-6 mx-4">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
            {isEdit ? "은행계좌 수정" : "은행계좌 추가"}
          </h2>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">계좌 별칭 *</label>
            <input type="text" required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="예: 국민은행 주계좌"
              className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">은행명</label>
            <input type="text" value={form.institution}
              onChange={(e) => setForm({ ...form, institution: e.target.value })}
              placeholder="예: 국민은행"
              className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          {!isEdit && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">계좌 종류</label>
              <select value={form.asset_type} onChange={(e) => setForm({ ...form, asset_type: e.target.value })}
                className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="BANK_ACCOUNT">입출금</option>
                <option value="DEPOSIT">예·적금</option>
                <option value="CASH_OTHER">현금/기타</option>
              </select>
            </div>
          )}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">잔액</label>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500 dark:text-gray-400 w-8 shrink-0">₩</span>
              <input
                type="number"
                value={depositKrw ?? ""}
                onChange={(e) => setDepositKrw(e.target.value === "" ? undefined : Number(e.target.value))}
                placeholder="0"
                min="0"
                className="flex-1 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500 dark:text-gray-400 w-8 shrink-0">$</span>
              <input
                type="number"
                value={depositUsd ?? ""}
                onChange={(e) => setDepositUsd(e.target.value === "" ? undefined : Number(e.target.value))}
                placeholder="0"
                min="0"
                step="0.01"
                className="flex-1 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            {(depositUsd ?? 0) > 0 && (
              <p className="text-xs text-gray-500 dark:text-gray-400 pl-10">
                {usdRate == null
                  ? "환율 정보를 불러오는 중..."
                  : `≈ ${fmtKrw(usdAsKrw)} (환율 ${usdRate.toLocaleString()}원/USD)`}
              </p>
            )}
            {((depositKrw ?? 0) > 0 || (depositUsd ?? 0) > 0) && (
              <p className="text-xs font-medium text-gray-700 dark:text-gray-300 pl-10">
                합계: {fmtKrw(totalKrw)}
              </p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">메모</label>
            <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="선택 입력" rows={2}
              className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">취소</button>
            <button type="submit" disabled={isLoading || usdPending}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {isLoading ? "저장 중..." : isEdit ? "저장" : "추가"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
