import { useEffect, useRef, useState } from "react";
import { Plus, Trash2, X } from "lucide-react";
import { AssetAccount, searchStocks, StockSuggestion } from "../../api/assets";
import { Portfolio, PortfolioItem } from "../../api/portfolios";

interface Props {
  initial?: Portfolio | null;
  accounts?: AssetAccount[];  // 주식 계좌 목록 (STOCK_KIS, STOCK_OTHER)
  onSave: (name: string, items: PortfolioItem[], baseType: string, accountIds: string[] | null) => void;
  onClose: () => void;
  saving?: boolean;
}

const EMPTY_ITEM: PortfolioItem = { ticker: "", name: "", market: "KOSPI", weight: 0 };

export default function UnifiedPortfolioEditor({ initial, accounts = [], onSave, onClose, saving }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [baseType, setBaseType] = useState(initial?.base_type ?? "STOCK_ONLY");
  const [items, setItems] = useState<PortfolioItem[]>(
    initial?.items.length ? initial.items : [{ ...EMPTY_ITEM }]
  );
  const [suggestions, setSuggestions] = useState<StockSuggestion[]>([]);
  const [activeRow, setActiveRow] = useState<number | null>(null);
  const [editingRows, setEditingRows] = useState<Set<number>>(new Set());
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchInputRefs = useRef<Map<number, HTMLInputElement>>(new Map());

  // 계좌 선택 상태: null이면 모든 계좌, 배열이면 선택된 계좌만
  const [selectedAccountIds, setSelectedAccountIds] = useState<Set<string>>(() => {
    if (initial?.account_ids?.length) {
      return new Set(initial.account_ids);
    }
    return new Set(accounts.map((a) => a.id));
  });

  // accounts prop이 바뀌면 새 계좌를 기본 선택에 추가
  useEffect(() => {
    if (!initial?.account_ids?.length) {
      setSelectedAccountIds(new Set(accounts.map((a) => a.id)));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accounts.map((a) => a.id).sort().join(",")]);

  const isAllSelected = accounts.length === 0 || accounts.every((a) => selectedAccountIds.has(a.id));

  function toggleAccount(id: string) {
    setSelectedAccountIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  const totalWeight = items.reduce((s, i) => s + (Number(i.weight) || 0), 0);
  const weightOk = Math.abs(totalWeight - 100) < 0.01;

  function updateItem(idx: number, patch: Partial<PortfolioItem>) {
    setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  function removeItem(idx: number) {
    setItems((prev) => prev.filter((_, i) => i !== idx));
  }

  function addCash() {
    if (items.some((i) => i.ticker === "CASH")) return;
    setItems((prev) => [...prev, { ticker: "CASH", name: "현금", market: "KRW", weight: 0 }]);
  }

  function addRealEstate() {
    if (items.some((i) => i.market === "KR_PROPERTY")) return;
    setItems((prev) => [...prev, { ticker: "REAL_ESTATE", name: "부동산", market: "KR_PROPERTY", weight: 0 }]);
  }

  function handleTickerInput(idx: number, value: string) {
    updateItem(idx, { ticker: value });
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (value.length < 1) { setSuggestions([]); return; }
    searchTimer.current = setTimeout(async () => {
      setActiveRow(idx);
      const results = await searchStocks(value);
      setSuggestions(results);
    }, 300);
  }

  function selectSuggestion(idx: number, s: StockSuggestion) {
    updateItem(idx, { ticker: s.ticker, name: s.name, market: s.market });
    setSuggestions([]);
    setActiveRow(null);
    setEditingRows((prev) => { const next = new Set(prev); next.delete(idx); return next; });
  }

  function startEditing(idx: number) {
    updateItem(idx, { ticker: "", name: "" });
    setEditingRows((prev) => new Set(prev).add(idx));
    setSuggestions([]);
    setTimeout(() => searchInputRefs.current.get(idx)?.focus(), 0);
  }

  function handleSubmit() {
    if (!name.trim() || !weightOk) return;
    const accountIds = isAllSelected ? null : Array.from(selectedAccountIds);
    onSave(name.trim(), items, baseType, accountIds);
  }

  useEffect(() => {
    const handler = () => { setSuggestions([]); setActiveRow(null); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-gray-700">
          <h2 className="font-semibold text-gray-800 dark:text-gray-50">
            {initial ? "포트폴리오 수정" : "새 포트폴리오 만들기"}
          </h2>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-50 dark:text-gray-500 dark:hover:text-gray-300 dark:hover:bg-gray-800 rounded-lg transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
          {/* 이름 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">포트폴리오 이름</label>
            <input
              className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 placeholder-gray-400 dark:placeholder-gray-500 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="예: 성장형 포트폴리오"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {/* 기준 자산 (리밸런싱용) */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">리밸런싱 기준 자산</label>
            <div className="flex gap-4">
              {[
                { value: "STOCK_ONLY", label: "주식 자산만" },
                { value: "TOTAL_ASSETS", label: "전체 자산" },
              ].map(({ value, label }) => (
                <label key={value} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="baseType"
                    value={value}
                    checked={baseType === value}
                    onChange={() => setBaseType(value)}
                    className="accent-blue-600"
                  />
                  <span className="text-sm text-gray-700 dark:text-gray-300">{label}</span>
                </label>
              ))}
            </div>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">백테스팅에는 영향 없음. 현금·부동산 항목은 백테스팅에서 자동 제외됩니다.</p>
          </div>

          {/* 종목 목록 */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">종목 및 비중</label>
              <span className={`text-xs font-medium ${weightOk ? "text-green-600" : "text-orange-500"}`}>
                합계 {totalWeight.toFixed(1)}% {weightOk ? "✓" : "(100% 필요)"}
              </span>
            </div>

            <div className="space-y-2">
              {items.map((item, idx) => (
                <div key={idx} className="relative flex items-center gap-2">
                  {item.ticker === "CASH" ? (
                    <div className="flex-1 flex items-center gap-2 border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2">
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400 bg-gray-200 dark:bg-gray-700 px-2 py-0.5 rounded">현금</span>
                      <span className="text-sm text-gray-700 dark:text-gray-300 flex-1">KRW 현금</span>
                    </div>
                  ) : item.market === "KR_PROPERTY" ? (
                    <div className="flex-1 flex items-center gap-2 border border-amber-200 dark:border-amber-700/50 bg-amber-50 dark:bg-amber-900/20 rounded-lg px-3 py-2">
                      <span className="text-xs font-medium text-amber-700 bg-amber-200 px-2 py-0.5 rounded">부동산</span>
                      <span className="text-sm text-gray-700 dark:text-gray-300 flex-1">REAL_ESTATE (순자산 합산)</span>
                    </div>
                  ) : item.ticker && item.name && !editingRows.has(idx) ? (
                    /* 표시 모드: 종목 선택 완료 */
                    <div className="flex-1 flex items-center justify-between gap-2 border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2">
                      <div className="flex items-baseline gap-2 min-w-0">
                        <span className="text-sm font-semibold text-gray-800 dark:text-gray-50 truncate">{item.name}</span>
                        <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">{item.ticker} · {item.market}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => startEditing(idx)}
                        className="text-xs text-blue-500 hover:text-blue-700 whitespace-nowrap flex-shrink-0"
                      >
                        변경
                      </button>
                    </div>
                  ) : (
                    /* 검색 모드: 종목 입력/검색 */
                    <div className="flex-1 relative">
                      <input
                        ref={(el) => {
                          if (el) searchInputRefs.current.set(idx, el);
                          else searchInputRefs.current.delete(idx);
                        }}
                        className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 placeholder-gray-400 dark:placeholder-gray-500 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        placeholder="종목명 또는 티커 검색 (예: 삼성전자, AAPL)"
                        value={item.ticker}
                        onChange={(e) => handleTickerInput(idx, e.target.value)}
                        onFocus={() => setActiveRow(idx)}
                      />
                      {activeRow === idx && suggestions.length > 0 && (
                        <div
                          className="absolute z-10 top-full left-0 right-0 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg mt-1 max-h-48 overflow-y-auto"
                          onMouseDown={(e) => e.stopPropagation()}
                        >
                          {suggestions.map((s) => (
                            <button
                              key={`${s.ticker}-${s.market}`}
                              className="w-full text-left px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-900/30 flex items-center gap-2 text-sm"
                              onMouseDown={() => selectSuggestion(idx, s)}
                            >
                              <span className="font-medium text-gray-800 dark:text-gray-50 flex-1 truncate">{s.name}</span>
                              <span className="text-xs text-gray-400 dark:text-gray-500">{s.ticker}</span>
                              <span className="text-xs text-gray-400 dark:text-gray-500 ml-1">{s.market}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.1}
                    className="w-24 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm text-right focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="비중 %"
                    value={item.weight || ""}
                    onChange={(e) => updateItem(idx, { weight: parseFloat(e.target.value) || 0 })}
                  />
                  <span className="text-sm text-gray-500 dark:text-gray-400">%</span>
                  <button
                    onClick={() => removeItem(idx)}
                    className="p-1.5 text-gray-400 dark:text-gray-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
            </div>

            <div className="flex gap-2 mt-3">
              <button
                onClick={() => setItems((prev) => [...prev, { ...EMPTY_ITEM }])}
                className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 px-2 py-1 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
              >
                <Plus size={14} /> 종목 추가
              </button>
              <button
                onClick={addCash}
                disabled={items.some((i) => i.ticker === "CASH")}
                className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 px-2 py-1 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-40"
              >
                <Plus size={14} /> 현금 추가
              </button>
              <button
                onClick={addRealEstate}
                disabled={items.some((i) => i.market === "KR_PROPERTY")}
                className="flex items-center gap-1 text-sm text-amber-600 hover:text-amber-700 px-2 py-1 rounded-lg hover:bg-amber-50 transition-colors disabled:opacity-40"
              >
                <Plus size={14} /> 부동산 추가
              </button>
            </div>
          </div>
          {/* 분석 대상 계좌 — 주식 계좌가 2개 이상일 때만 표시 */}
          {accounts.length > 1 && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">분석 대상 계좌</label>
                {!isAllSelected && (
                  <button
                    type="button"
                    onClick={() => setSelectedAccountIds(new Set(accounts.map((a) => a.id)))}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    전체 선택
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-x-5 gap-y-1.5 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                {accounts.map((acc) => (
                  <label key={acc.id} className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedAccountIds.has(acc.id)}
                      onChange={() => toggleAccount(acc.id)}
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
                {isAllSelected ? "모든 주식 계좌가 리밸런싱 분석에 포함됩니다." : `${selectedAccountIds.size}개 계좌만 분석에 포함됩니다.`}
              </p>
            </div>
          )}
        </div>

        {/* 하단 버튼 */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-100 dark:border-gray-700">
          <button
            onClick={onClose}
            className="px-5 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            취소
          </button>
          <button
            onClick={handleSubmit}
            disabled={!name.trim() || !weightOk || saving}
            className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {saving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
