import type { OverseasPositionDetail } from "@/api/tax";
import { fmtKrw, fmtPct } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { posKey, TAX_RATE } from "@/hooks/useTaxSimulation";

interface Props {
  kind: "profit" | "loss";
  positions: OverseasPositionDetail[];
  sellQtyMap: Record<string, number>;
  maxTaxFreeProfit: number;
  totalLoss: number;
  hasAnyQtyInput: boolean;
  handleQtyChange: (pos: OverseasPositionDetail, val: string) => void;
}

function QtyInput({ pos, qty, handleQtyChange }: {
  pos: OverseasPositionDetail;
  qty: number;
  handleQtyChange: (pos: OverseasPositionDetail, val: string) => void;
}) {
  return (
    <div className="flex items-center gap-1">
      <input
        type="number"
        min={0}
        max={Math.floor(pos.qty)}
        step={1}
        value={qty === 0 ? "" : qty}
        onChange={(e) => handleQtyChange(pos, e.target.value)}
        placeholder="0"
        className="w-16 border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded px-1.5 py-1 text-xs text-right focus:outline-none focus:ring-1 focus:ring-blue-400"
      />
      <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">/ {Math.floor(pos.qty)}주</span>
    </div>
  );
}

export function TaxPositionTable({
  kind, positions, sellQtyMap, maxTaxFreeProfit, totalLoss, hasAnyQtyInput, handleQtyChange,
}: Props) {
  const isLoss = kind === "loss";

  return (
    <>
      {/* 모바일: 카드 레이아웃 */}
      <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-800">
        {positions.map((pos) => {
          const qty = sellQtyMap[posKey(pos)] ?? 0;
          const pnlPs = pos.qty > 0 ? pos.unrealized_pnl_krw / pos.qty : 0;
          const rowSimPnl = pnlPs * qty;
          const taxSaved = isLoss ? Math.round(Math.abs(rowSimPnl) * TAX_RATE) : 0;
          const isWithinBudget = !isLoss && pos.unrealized_pnl_krw <= maxTaxFreeProfit;

          return (
            <div key={posKey(pos)} className="px-4 py-2 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-1 min-w-0">
                  <span className="font-medium text-sm text-gray-800 dark:text-gray-200">{pos.ticker}</span>
                  <span className="text-gray-400 dark:text-gray-500 text-xs">{pos.market}</span>
                  {isWithinBudget && (
                    <span className="px-1 py-0.5 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 rounded text-xs font-medium">
                      무세 실현 가능
                    </span>
                  )}
                  <span className="text-gray-400 dark:text-gray-500 text-xs truncate">· {pos.name}</span>
                </div>
                <span className={`text-sm font-medium shrink-0 ${pnlColor(pos.unrealized_pnl_pct)}`}>
                  {fmtPct(pos.unrealized_pnl_pct)}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className={`text-sm font-medium ${pnlColor(pos.unrealized_pnl_krw)}`}>
                  {fmtKrw(pos.unrealized_pnl_krw)}
                  {qty > 0 && (
                    <span className={`ml-1.5 text-xs ${pnlColor(rowSimPnl)}`}>
                      ({qty}주: {fmtKrw(rowSimPnl)})
                    </span>
                  )}
                </span>
                <div className="shrink-0 text-right">
                  <div className="flex items-center gap-1 justify-end">
                    <QtyInput pos={pos} qty={qty} handleQtyChange={handleQtyChange} />
                  </div>
                  {isLoss && qty > 0 && (
                    <div className="text-xs text-blue-500 dark:text-blue-400 font-medium mt-0.5">
                      최대 {fmtKrw(taxSaved)} 절세
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
        {isLoss && totalLoss < 0 && !hasAnyQtyInput && (
          <div className="px-4 py-2.5 bg-blue-50 dark:bg-blue-900/20">
            <p className="text-xs text-blue-600 dark:text-blue-400">
              전량 매도 시 {fmtKrw(Math.abs(totalLoss))} 손실 통산 →{" "}
              수익 종목에서 추가로 {fmtKrw(Math.abs(totalLoss))}까지 세금 없이 실현 가능
            </p>
          </div>
        )}
      </div>

      {/* 데스크탑: 테이블 레이아웃 */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-800">
              <th className="px-2 py-2 sm:px-4 text-left font-medium">종목</th>
              <th className="px-2 py-2 sm:px-4 text-right font-medium">
                {isLoss ? "미실현 손실" : "미실현 수익"}
              </th>
              <th className="px-2 py-2 sm:px-4 text-right font-medium">
                {isLoss ? "손실률" : "수익률"}
              </th>
              <th className="px-2 py-2 sm:px-4 text-right font-medium">매도 수량</th>
              {isLoss && <th className="px-2 py-2 sm:px-4 text-right font-medium">통산 절세 효과</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
            {positions.map((pos) => {
              const qty = sellQtyMap[posKey(pos)] ?? 0;
              const pnlPs = pos.qty > 0 ? pos.unrealized_pnl_krw / pos.qty : 0;
              const rowSimPnl = pnlPs * qty;
              const taxSaved = isLoss ? Math.round(Math.abs(rowSimPnl) * TAX_RATE) : 0;
              const isWithinBudget = !isLoss && pos.unrealized_pnl_krw <= maxTaxFreeProfit;

              return (
                <tr key={posKey(pos)} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="px-2 py-2.5 sm:px-4">
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium text-gray-800 dark:text-gray-200">{pos.ticker}</span>
                      <span className="text-gray-400 dark:text-gray-500 text-xs">{pos.market}</span>
                      {isWithinBudget && (
                        <span className="ml-1 px-1.5 py-0.5 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 rounded text-xs font-medium">
                          무세 실현 가능
                        </span>
                      )}
                    </div>
                    <div className="text-gray-400 dark:text-gray-500 mt-0.5">{pos.name}</div>
                  </td>
                  <td className="px-2 py-2.5 sm:px-4 text-right">
                    <span className={`font-medium ${pnlColor(pos.unrealized_pnl_krw)}`}>
                      {fmtKrw(pos.unrealized_pnl_krw)}
                    </span>
                    {qty > 0 && (
                      <div className={`text-xs ${pnlColor(rowSimPnl)}`}>
                        {qty}주: {fmtKrw(rowSimPnl)}
                      </div>
                    )}
                  </td>
                  <td className="px-2 py-2.5 sm:px-4 text-right">
                    <span className={pnlColor(pos.unrealized_pnl_pct)}>
                      {fmtPct(pos.unrealized_pnl_pct)}
                    </span>
                  </td>
                  <td className="px-2 py-2.5 sm:px-4 text-right">
                    <QtyInput pos={pos} qty={qty} handleQtyChange={handleQtyChange} />
                  </td>
                  {isLoss && (
                    <td className="px-2 py-2.5 sm:px-4 text-right">
                      {qty === 0 ? (
                        <span className="text-gray-300 dark:text-gray-600">—</span>
                      ) : (
                        <span className="text-blue-500 dark:text-blue-400 font-medium">
                          최대 {fmtKrw(taxSaved)} 절세
                        </span>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
          {isLoss && totalLoss < 0 && !hasAnyQtyInput && (
            <tfoot>
              <tr>
                <td colSpan={5} className="px-4 py-2.5 bg-blue-50 dark:bg-blue-900/20">
                  <p className="text-xs text-blue-600 dark:text-blue-400">
                    전량 매도 시 {fmtKrw(Math.abs(totalLoss))} 손실 통산 →{" "}
                    수익 종목에서 추가로 {fmtKrw(Math.abs(totalLoss))}까지 세금 없이 실현 가능
                  </p>
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </>
  );
}
