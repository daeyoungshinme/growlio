import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { HoldingItem, BacktestPortfolioConfig } from "../../api/backtest";

const MARKETS = ["NASDAQ", "NYSE", "KOSPI", "KOSDAQ", "KRX", "기타"];

interface Props {
  initial?: BacktestPortfolioConfig;
  onSave: (name: string, holdings: HoldingItem[]) => void;
  onClose: () => void;
  isSaving: boolean;
}

export default function PortfolioEditor({ initial, onSave, onClose, isSaving }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [holdings, setHoldings] = useState<HoldingItem[]>(
    initial?.holdings.length ? initial.holdings : [{ ticker: "", market: "NASDAQ", weight: 100 }]
  );

  const totalWeight = holdings.reduce((s, h) => s + (h.weight || 0), 0);
  const weightOk = Math.abs(totalWeight - 100) < 0.01;

  const addRow = () => setHoldings((prev) => [...prev, { ticker: "", market: "NASDAQ", weight: 0 }]);

  const removeRow = (i: number) => setHoldings((prev) => prev.filter((_, idx) => idx !== i));

  const update = (i: number, field: keyof HoldingItem, value: string | number) =>
    setHoldings((prev) => prev.map((h, idx) => (idx === i ? { ...h, [field]: value } : h)));

  const handleSave = () => {
    if (!name.trim()) return;
    if (!weightOk) return;
    const valid = holdings.filter((h) => h.ticker.trim());
    if (!valid.length) return;
    onSave(name.trim(), valid);
  };

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl w-full max-w-lg">
        <div className="p-5 border-b border-gray-100 dark:border-gray-700">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50">
            {initial ? "포트폴리오 수정" : "새 포트폴리오"}
          </h3>
        </div>

        <div className="p-5 space-y-4">
          {/* 이름 */}
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">포트폴리오 이름</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="예: 미국 성장주 포트폴리오"
            />
          </div>

          {/* 종목 목록 */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400">종목 구성</label>
              <span className={`text-xs font-medium ${weightOk ? "text-green-600 dark:text-green-400" : "text-red-500"}`}>
                합계: {totalWeight.toFixed(1)}%
              </span>
            </div>
            <div className="space-y-2">
              <div className="grid grid-cols-[1fr_120px_72px_32px] gap-2 text-xs text-gray-400 dark:text-gray-500 font-medium px-1">
                <span>티커</span>
                <span>시장</span>
                <span>비중(%)</span>
                <span />
              </div>
              {holdings.map((h, i) => (
                <div key={i} className="grid grid-cols-[1fr_120px_72px_32px] gap-2 items-center">
                  <input
                    type="text"
                    value={h.ticker}
                    onChange={(e) => update(i, "ticker", e.target.value.toUpperCase())}
                    className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="AAPL"
                  />
                  <select
                    value={h.market}
                    onChange={(e) => update(i, "market", e.target.value)}
                    className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {MARKETS.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <input
                    type="number"
                    value={h.weight}
                    min={0}
                    max={100}
                    step={0.1}
                    onChange={(e) => update(i, "weight", parseFloat(e.target.value) || 0)}
                    className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2 py-1.5 text-sm text-right focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <button
                    onClick={() => removeRow(i)}
                    disabled={holdings.length === 1}
                    className="p-1 text-gray-300 dark:text-gray-600 hover:text-red-500 disabled:opacity-30 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
            <button
              onClick={addRow}
              className="mt-2 flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors"
            >
              <Plus size={12} /> 종목 추가
            </button>
          </div>
        </div>

        <div className="p-5 border-t border-gray-100 dark:border-gray-700 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            취소
          </button>
          <button
            onClick={handleSave}
            disabled={!name.trim() || !weightOk || isSaving}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {isSaving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
