import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { fmtKrwShort } from "../../utils/format";
import { pnlColor } from "../../utils/colors";
import { STOCK_TYPE_LABELS, DATA_SOURCE_BADGE } from "../../constants";
import type { AccountRow } from "../../types";

function PnlText({ val, pct }: { val: number; pct: number }) {
  const pos = val >= 0;
  return (
    <span className={pnlColor(val)}>
      {pos ? "+" : ""}{fmtKrwShort(val)}원 ({pos ? "+" : ""}{pct.toFixed(2)}%)
    </span>
  );
}

interface Props {
  acc: AccountRow;
  onSync: () => void;
  syncing: boolean;
}

export default function AccountCard({ acc, onSync, syncing }: Props) {
  const [open, setOpen] = useState(false);
  const hasPositions = acc.positions.length > 0;

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4">
        <button
          className="flex-1 flex items-center gap-3 text-left min-w-0"
          onClick={() => hasPositions && setOpen((v) => !v)}
        >
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-gray-900 dark:text-gray-50">{acc.name}</span>
              <span className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 px-2 py-0.5 rounded-full">
                {STOCK_TYPE_LABELS[acc.asset_type] ?? acc.asset_type_label}
              </span>
              {acc.data_source !== "MANUAL" && (
                <span className={`text-xs px-2 py-0.5 rounded-full ${DATA_SOURCE_BADGE[acc.data_source] ?? "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"}`}>
                  {acc.data_source}
                </span>
              )}
            </div>
            {acc.institution && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate">{acc.institution}</p>}
          </div>
        </button>

        <div className="flex items-center gap-4 shrink-0 ml-4">
          <div className="text-right">
            <p className="font-bold text-gray-900 dark:text-gray-50">{fmtKrwShort(acc.amount_krw)}원</p>
            {acc.invested_krw > 0 && (
              <p className="text-xs">
                <PnlText val={acc.unrealized_pnl} pct={acc.invested_krw ? acc.unrealized_pnl / acc.invested_krw * 100 : 0} />
              </p>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button onClick={onSync} disabled={syncing} title="동기화"
              className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors disabled:opacity-40">
              <RefreshCw size={15} className={syncing ? "animate-spin" : ""} />
            </button>
            {hasPositions && (
              <button onClick={() => setOpen((v) => !v)}
                className="p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors text-xs">
                {open ? "▲" : "▼"}
              </button>
            )}
          </div>
        </div>
      </div>

      {open && hasPositions && (
        <div className="border-t border-gray-100 dark:border-gray-700 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-800 text-xs text-gray-400 dark:text-gray-500 tracking-wide">
                <th className="text-left px-5 py-2.5 font-medium">종목</th>
                <th className="text-right px-3 py-2.5 font-medium">보유수</th>
                <th className="text-right px-3 py-2.5 font-medium">평단가</th>
                <th className="text-right px-3 py-2.5 font-medium">현재가</th>
                <th className="text-right px-3 py-2.5 font-medium">매입금액</th>
                <th className="text-right px-3 py-2.5 font-medium">평가금액</th>
                <th className="text-right px-5 py-2.5 font-medium">수익률</th>
              </tr>
            </thead>
            <tbody>
              {acc.positions.map((p) => (
                <tr key={`${p.ticker}-${p.market}`} className="border-t border-gray-50 dark:border-gray-800 hover:bg-blue-50/30 dark:hover:bg-blue-950/20">
                  <td className="px-5 py-3">
                    <p className="font-medium text-gray-900 dark:text-gray-50">{p.name}</p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">{p.ticker} · {p.market}</p>
                  </td>
                  <td className="px-3 py-3 text-right">{p.qty.toLocaleString()}주</td>
                  <td className="px-3 py-3 text-right text-gray-500 dark:text-gray-400">{p.avg_price.toLocaleString()}</td>
                  <td className="px-3 py-3 text-right font-medium">{p.current_price.toLocaleString()}</td>
                  <td className="px-3 py-3 text-right text-gray-500 dark:text-gray-400">{fmtKrwShort(p.invested_krw)}원</td>
                  <td className="px-3 py-3 text-right font-medium">{fmtKrwShort(p.value_krw)}원</td>
                  <td className="px-5 py-3 text-right text-sm">
                    <PnlText val={p.pnl} pct={p.pnl_pct} />
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="bg-gray-50 dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 text-sm font-semibold">
                <td className="px-5 py-3 text-gray-500 dark:text-gray-400">합계</td>
                <td colSpan={3} />
                <td className="px-3 py-3 text-right">{fmtKrwShort(acc.invested_krw)}원</td>
                <td className="px-3 py-3 text-right">{fmtKrwShort(acc.amount_krw)}원</td>
                <td className="px-5 py-3 text-right text-sm">
                  <PnlText val={acc.unrealized_pnl} pct={acc.invested_krw ? acc.unrealized_pnl / acc.invested_krw * 100 : 0} />
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
