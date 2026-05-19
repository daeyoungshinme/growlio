import { useState } from "react";
import { X } from "lucide-react";

interface Props {
  ticker: string;
  market: string;
  name: string;
  currentMonths: number[];
  isManual: boolean;
  onClose: () => void;
  onSave: (months: number[]) => void;
  onReset: () => void;
  isSaving: boolean;
}

const MONTH_LABELS = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"];

export default function DividendMonthsModal({
  ticker, market, name, currentMonths, isManual, onClose, onSave, onReset, isSaving,
}: Props) {
  const [selected, setSelected] = useState<Set<number>>(new Set(currentMonths));

  const toggle = (m: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(m) ? next.delete(m) : next.add(m);
      return next;
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl w-80 p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="font-semibold text-gray-900 dark:text-gray-50">{name}</p>
            <p className="text-xs text-gray-400 dark:text-gray-500">{ticker} · {market}</p>
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
            <X size={16} />
          </button>
        </div>

        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">배당 지급 월 선택 (복수 선택 가능)</p>

        <div className="grid grid-cols-4 gap-2 mb-5">
          {MONTH_LABELS.map((label, i) => {
            const m = i + 1;
            const active = selected.has(m);
            return (
              <button
                key={m}
                onClick={() => toggle(m)}
                className={`py-2 rounded-lg text-xs font-medium transition-colors border ${
                  active
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:border-blue-300 hover:text-blue-600"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>

        <div className="flex gap-2">
          {isManual && (
            <button
              onClick={onReset}
              disabled={isSaving}
              className="flex-1 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
            >
              자동으로 복구
            </button>
          )}
          <button
            onClick={() => onSave(Array.from(selected).sort((a, b) => a - b))}
            disabled={isSaving}
            className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {isSaving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
