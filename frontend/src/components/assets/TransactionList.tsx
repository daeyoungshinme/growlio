import { Pencil, Trash2 } from "lucide-react";
import { Transaction, TransactionCreate } from "@/api/transactions";
import { fmtKrw } from "@/utils/format";
import { TX_LABELS, TX_COLORS } from "@/constants/transaction";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";

interface TransactionListProps {
  txList: Transaction[] | undefined;
  isLoading: boolean;
  activeType: TransactionCreate["transaction_type"];
  isDeleting: boolean;
  onEdit: (tx: Transaction) => void;
  onDelete: (id: string) => void;
}

export function TransactionList({
  txList,
  isLoading,
  activeType,
  isDeleting,
  onEdit,
  onDelete,
}: TransactionListProps) {
  const filtered = (txList ?? []).filter((t) => t.transaction_type === activeType);

  if (isLoading) {
    return (
      <div className="py-8 text-center text-gray-300 dark:text-gray-600 text-sm">로딩 중...</div>
    );
  }

  if (filtered.length === 0) {
    return (
      <div className="py-8 text-center text-gray-300 dark:text-gray-600 text-sm">
        등록된 내역이 없습니다
      </div>
    );
  }

  return (
    <>
      {/* 모바일 카드 뷰 */}
      <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-800">
        {filtered.map((tx) => (
          <div key={tx.id} className="px-3 py-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-medium ${TX_COLORS[tx.transaction_type]}`}>
                    {TX_LABELS[tx.transaction_type]}
                  </span>
                  {tx.ticker && (
                    <span className="text-xs text-gray-400 dark:text-gray-500">{tx.ticker}</span>
                  )}
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                  {tx.transaction_date}
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <p className="font-semibold text-gray-900 dark:text-gray-50 text-sm">
                  {fmtKrw(tx.amount)}
                </p>
                <button
                  onClick={() => onEdit(tx)}
                  aria-label="수정"
                  className={`${TOUCH_TARGET_MIN} p-1.5 text-gray-300 dark:text-gray-600 hover:text-blue-400 transition-colors`}
                >
                  <Pencil size={13} />
                </button>
                <button
                  onClick={() => onDelete(tx.id)}
                  disabled={isDeleting}
                  aria-label="삭제"
                  className={`${TOUCH_TARGET_MIN} p-1.5 text-gray-300 dark:text-gray-600 hover:text-red-400 transition-colors`}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
            {tx.notes && (
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 truncate">{tx.notes}</p>
            )}
          </div>
        ))}
      </div>

      {/* 데스크탑 테이블 */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
              <th className="text-left px-3 py-2.5 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">
                날짜
              </th>
              <th className="text-left px-3 py-2.5 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">
                구분
              </th>
              <th className="text-right px-3 py-2.5 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">
                금액
              </th>
              <th className="text-left px-3 py-2.5 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">
                메모
              </th>
              <th className="px-3 py-2.5" />
            </tr>
          </thead>
          <tbody>
            {filtered.map((tx) => (
              <tr
                key={tx.id}
                className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                <td className="px-3 py-3 text-gray-500 dark:text-gray-400 whitespace-nowrap text-xs">
                  {tx.transaction_date}
                </td>
                <td
                  className={`px-3 py-3 font-medium whitespace-nowrap ${TX_COLORS[tx.transaction_type]}`}
                >
                  <span>{TX_LABELS[tx.transaction_type]}</span>
                  {tx.ticker && (
                    <span className="block text-xs text-gray-400 dark:text-gray-500 font-normal mt-0.5">
                      {tx.ticker}
                    </span>
                  )}
                </td>
                <td className="px-3 py-3 text-right font-semibold text-gray-900 dark:text-gray-50 whitespace-nowrap">
                  {fmtKrw(tx.amount)}
                </td>
                <td className="px-3 py-3 text-gray-400 dark:text-gray-500 text-xs">
                  <div className="max-w-[100px] truncate">{tx.notes || "—"}</div>
                </td>
                <td className="px-3 py-3 text-right">
                  <div className="flex justify-end gap-1">
                    <button
                      onClick={() => onEdit(tx)}
                      aria-label="수정"
                      className="p-1 text-gray-300 dark:text-gray-600 hover:text-blue-400 transition-colors"
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      onClick={() => onDelete(tx.id)}
                      disabled={isDeleting}
                      aria-label="삭제"
                      className="p-1 text-gray-300 dark:text-gray-600 hover:text-red-400 transition-colors"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
