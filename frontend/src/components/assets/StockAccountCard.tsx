import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart2, Loader2, Pencil, Receipt, RefreshCw, Trash2 } from "lucide-react";
import { fetchExchangeRate, type AssetAccount } from "../../api/assets";
import { fmtKrw } from "../../utils/format";
import { pnlColor } from "../../utils/colors";
import { STOCK_TYPE_LABELS } from "../../constants";

export interface AccountStats {
  amount_krw: number;
  invested_krw: number;
  unrealized_pnl: number;
  deposit_total: number;
  dividend_total: number;
}

interface Props {
  account: AssetAccount;
  stats?: AccountStats;
  onDelete: (id: string) => void;
  onManagePositions: (account: { id: string; name: string; dataSource: string }) => void;
  onTransactions: (account: { id: string; name: string }) => void;
  onEditDeposit: (id: string, amount: number) => void;
  onEditName: (id: string, name: string) => void;
  onSync: (id: string) => void;
  isSyncing: boolean;
  isDeleting: boolean;
}

export default function StockAccountCard({ account, stats, onDelete, onManagePositions, onTransactions, onEditDeposit, onEditName, onSync, isSyncing, isDeleting }: Props) {
  const typeLabel = STOCK_TYPE_LABELS[account.asset_type] ?? account.asset_type;
  const accountNo = account.kis_account_no ?? account.kiwoom_account_no ?? null;
  const hasStats = stats && (stats.amount_krw > 0 || stats.deposit_total > 0 || stats.dividend_total > 0);
  const pnl = stats?.unrealized_pnl ?? 0;
  const ret = stats?.invested_krw ? (pnl / stats.invested_krw) * 100 : 0;
  const [editNameMode, setEditNameMode] = useState(false);
  const [editNameValue, setEditNameValue] = useState(account.name);
  const [editDepositMode, setEditDepositMode] = useState(false);
  const [editDepositValue, setEditDepositValue] = useState("");
  const [depositCurrency, setDepositCurrency] = useState<"KRW" | "USD">("KRW");
  const [depositUsdValue, setDepositUsdValue] = useState<number>(0);
  const { data: rateData } = useQuery({
    queryKey: ["exchange-rate"],
    queryFn: fetchExchangeRate,
    staleTime: 5 * 60 * 1000,
  });
  const usdRate = rateData?.usd_krw ?? null;

  const handleSaveName = () => {
    const trimmed = editNameValue.trim();
    if (trimmed) {
      onEditName(account.id, trimmed);
      setEditNameMode(false);
    }
  };

  const handleSave = () => {
    const krwAmount = depositCurrency === "USD"
      ? Math.round(depositUsdValue * (usdRate ?? 1))
      : Number(editDepositValue);
    onEditDeposit(account.id, krwAmount);
    setEditDepositMode(false);
  };

  const handleCancel = () => {
    setEditDepositMode(false);
    setDepositCurrency("KRW");
    setDepositUsdValue(0);
  };

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {/* 줄1: 증권사명 · 계좌명 + 편집버튼 */}
          <div className="flex items-center gap-1.5 min-w-0">
            {editNameMode ? (
              <>
                <input
                  type="text"
                  value={editNameValue}
                  autoFocus
                  onChange={(e) => setEditNameValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSaveName();
                    if (e.key === "Escape") { setEditNameMode(false); setEditNameValue(account.name); }
                  }}
                  className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2 py-0.5 text-sm w-40 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button onClick={handleSaveName} className="text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium">저장</button>
                <button onClick={() => { setEditNameMode(false); setEditNameValue(account.name); }} className="text-xs text-gray-400 dark:text-gray-500 hover:underline">취소</button>
              </>
            ) : (
              <>
                {account.institution && (
                  <span className="text-base text-gray-400 dark:text-gray-500 shrink-0">{account.institution} ·</span>
                )}
                <span className="text-base font-semibold text-gray-900 dark:text-gray-50 truncate">{account.name}</span>
                <button
                  onClick={() => { setEditNameValue(account.name); setEditNameMode(true); }}
                  title="계좌명 수정"
                  className="p-1.5 sm:p-0.5 text-gray-300 dark:text-gray-600 hover:text-blue-400 transition-colors shrink-0">
                  <Pencil size={12} />
                </button>
              </>
            )}
          </div>
          {/* 줄2: 계좌번호 + 배지 */}
          <div className="flex flex-wrap items-center gap-1.5 mt-1">
            {accountNo && (
              <span className="text-xs text-gray-400 dark:text-gray-500">{accountNo}</span>
            )}
            <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-xs rounded-full">{typeLabel}</span>
            {account.has_own_kis_credentials && (
              <span className="px-2 py-0.5 border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 text-xs rounded-full">전용 API 키</span>
            )}
            {account.has_own_kiwoom_credentials && (
              <span className="px-2 py-0.5 border border-amber-300 dark:border-amber-700 text-amber-600 dark:text-amber-400 text-xs rounded-full">키움 API 키</span>
            )}
          </div>
          {account.notes && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 truncate">{account.notes}</p>}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {(account.data_source === "KIS_API" || account.data_source === "KIWOOM_API") && (
            <button onClick={() => onSync(account.id)} disabled={isSyncing}
              title={account.data_source === "KIWOOM_API" ? "키움 데이터 동기화" : "KIS 데이터 동기화"}
              className="p-2.5 sm:p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors disabled:opacity-50">
              {isSyncing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            </button>
          )}
          <button onClick={() => onManagePositions({ id: account.id, name: account.name, dataSource: account.data_source })}
            title="종목 관리"
            className="p-2.5 sm:p-1.5 text-gray-400 hover:text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-950 rounded-lg transition-colors">
            <BarChart2 size={16} />
          </button>
          <button onClick={() => onTransactions({ id: account.id, name: account.name })}
            title="입출금 내역"
            className="p-2.5 sm:p-1.5 text-gray-400 hover:text-green-600 hover:bg-green-50 dark:hover:bg-green-950 rounded-lg transition-colors">
            <Receipt size={16} />
          </button>
          <button onClick={() => onDelete(account.id)} disabled={isDeleting}
            title="계좌 삭제"
            className="p-2.5 sm:p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors disabled:opacity-50">
            <Trash2 size={16} />
          </button>
        </div>
      </div>
      {hasStats && (
        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-5">
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">평가금액</p>
            <p className="text-xs font-semibold text-gray-900 dark:text-gray-50 mt-0.5">{fmtKrw(stats!.amount_krw)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">평가손익</p>
            <p className={`text-xs font-semibold mt-0.5 ${pnlColor(pnl)}`}>
              {pnl >= 0 ? "+" : ""}{fmtKrw(pnl)}
            </p>
            <p className={`text-xs ${pnlColor(ret)}`}>
              {ret >= 0 ? "+" : ""}{ret.toFixed(2)}%
            </p>
          </div>
          <div>
            <div className="flex items-center justify-between">
              <p className="text-xs text-gray-400 dark:text-gray-500">예수금</p>
              {editDepositMode && (
                <div className="flex gap-0.5 text-xs">
                  {(["KRW", "USD"] as const).map((c) => (
                    <button key={c} type="button"
                      onClick={() => { setDepositCurrency(c); setDepositUsdValue(0); }}
                      className={`px-1.5 py-0.5 rounded transition-colors ${
                        depositCurrency === c ? "bg-blue-600 text-white" : "text-gray-400 hover:text-gray-600"
                      }`}>
                      {c}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {editDepositMode ? (
              depositCurrency === "USD" ? (
                <div>
                  <div className="flex items-center gap-1 mt-0.5">
                    <span className="text-xs text-gray-400 shrink-0">$</span>
                    <input
                      type="number" autoFocus step="0.01" min={0}
                      value={depositUsdValue || ""}
                      onChange={(e) => setDepositUsdValue(parseFloat(e.target.value) || 0)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleSave();
                        if (e.key === "Escape") handleCancel();
                      }}
                      className="w-20 border rounded px-1.5 py-0.5 text-xs"
                    />
                    <button onClick={handleSave} className="text-xs text-blue-500 hover:text-blue-700">저장</button>
                    <button onClick={handleCancel} className="text-xs text-gray-400">취소</button>
                  </div>
                  {usdRate && depositUsdValue > 0 && (
                    <p className="text-xs text-gray-400 mt-0.5">
                      ≈ {fmtKrw(Math.round(depositUsdValue * usdRate))}
                    </p>
                  )}
                </div>
              ) : (
                <div className="flex items-center gap-1 mt-0.5">
                  <input
                    type="number" autoFocus
                    value={editDepositValue}
                    onChange={(e) => setEditDepositValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSave();
                      if (e.key === "Escape") handleCancel();
                    }}
                    className="w-20 border rounded px-1.5 py-0.5 text-xs"
                  />
                  <button onClick={handleSave} className="text-xs text-blue-500 hover:text-blue-700">저장</button>
                  <button onClick={handleCancel} className="text-xs text-gray-400">취소</button>
                </div>
              )
            ) : (
              <div className="flex items-center gap-1 mt-0.5">
                <p className="text-xs font-semibold text-gray-700 dark:text-gray-300">{fmtKrw(account.deposit_krw ?? 0)}</p>
                <button
                  onClick={() => { setEditDepositValue(String(account.deposit_krw ?? 0)); setDepositCurrency("KRW"); setDepositUsdValue(0); setEditDepositMode(true); }}
                  className="p-1.5 sm:p-0.5 text-gray-300 hover:text-blue-400 transition-colors">
                  <Pencil size={12} />
                </button>
              </div>
            )}
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">누적 입금</p>
            <p className="text-xs font-semibold text-blue-600 dark:text-blue-400 mt-0.5">{fmtKrw(stats!.deposit_total)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">누적 배당</p>
            <p className="text-xs font-semibold text-green-600 dark:text-green-400 mt-0.5">{fmtKrw(stats!.dividend_total)}</p>
          </div>
        </div>
      )}
    </div>
  );
}
