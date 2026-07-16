import { RebalancingItem } from "@/api/rebalancing";
import { fmtKrw } from "@/utils/format";
import { PROFIT_COLOR, LOSS_COLOR } from "@/utils/colors";
import { CASH_EQUIVALENT_TICKER, CASH_TICKER } from "@/constants/assets";

export function DiffCell({ diff }: { diff: number }) {
  if (diff === 0) return <span className="text-gray-500 dark:text-gray-400">-</span>;
  const isBuy = diff > 0;
  return (
    <span className={`font-medium ${isBuy ? PROFIT_COLOR : LOSS_COLOR}`}>
      {isBuy ? "+" : ""}
      {fmtKrw(diff)}
    </span>
  );
}

export function WeightDiffBadge({ diff }: { diff: number }) {
  if (Math.abs(diff) < 0.1)
    return <span className="text-gray-500 dark:text-gray-400 text-xs">±0%</span>;
  const isBuy = diff > 0;
  return (
    <span className={`text-xs font-medium ${isBuy ? PROFIT_COLOR : LOSS_COLOR}`}>
      {isBuy ? "▲" : "▼"} {Math.abs(diff).toFixed(1)}%
    </span>
  );
}

export function WeightBar({ current, target }: { current: number; target: number }) {
  const max = Math.max(current, target, 5);
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-2 bg-gray-300 dark:bg-gray-600 rounded-full overflow-hidden relative">
        <div
          className="absolute inset-y-0 left-0 bg-blue-400 rounded-full"
          style={{ width: `${Math.min((current / max) * 100, 100)}%` }}
        />
        <div
          className="absolute inset-y-0 left-0 border-r-2 border-orange-400"
          style={{ width: `${Math.min((target / max) * 100, 100)}%` }}
        />
      </div>
      <span className="text-xs text-gray-500 dark:text-gray-400 w-8 text-right">
        {target.toFixed(0)}%
      </span>
    </div>
  );
}

export function SharesCell({ item }: { item: RebalancingItem }) {
  if (item.ticker === CASH_TICKER || item.shares_to_trade === null)
    return <span className="text-gray-500 dark:text-gray-400">-</span>;
  const shares = item.shares_to_trade;
  if (shares === 0) return <span className="text-gray-500 dark:text-gray-400">0</span>;
  const isBuy = shares > 0;
  return (
    <span className={`font-medium text-xs ${isBuy ? PROFIT_COLOR : LOSS_COLOR}`}>
      {isBuy ? "+" : ""}
      {shares.toFixed(0)}주
    </span>
  );
}

export function QuantityCell({ item }: { item: RebalancingItem }) {
  if (item.ticker === CASH_TICKER || item.shares_to_trade === null)
    return <span className="text-gray-500 dark:text-gray-400">-</span>;

  const shares = item.shares_to_trade;
  const isBuy = shares > 0;
  const colorClass =
    shares === 0 ? "text-gray-500 dark:text-gray-400" : isBuy ? PROFIT_COLOR : LOSS_COLOR;

  const hasQty = item.current_qty != null && item.target_qty != null;

  return (
    <div className="text-right">
      {hasQty && (
        <div className="text-xs text-gray-500 dark:text-gray-400">
          {item.current_qty!.toFixed(0)}주 → {item.target_qty!.toFixed(0)}주
        </div>
      )}
      <div className={`font-medium text-xs ${colorClass}`}>
        {shares === 0 ? "0" : `${isBuy ? "+" : ""}${shares.toFixed(0)}주`}
      </div>
    </div>
  );
}

export function DividendDiffCell({ diff }: { diff: number }) {
  if (diff === 0) return <span className="text-gray-500 dark:text-gray-400">-</span>;
  const isIncrease = diff > 0;
  return (
    <span
      className={`font-medium text-xs ${isIncrease ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}
    >
      {isIncrease ? "+" : ""}
      {fmtKrw(diff)}
    </span>
  );
}

export function Return10yCell({ item }: { item: RebalancingItem }) {
  if (item.ticker === CASH_TICKER || item.ticker === CASH_EQUIVALENT_TICKER)
    return <span className="text-gray-600 dark:text-gray-500">-</span>;
  const cagr = item.cagr_10y_pct;
  const total = item.return_10y_pct;
  if (cagr == null || total == null)
    return <span className="text-gray-600 dark:text-gray-500">—</span>;
  const isPos = cagr >= 0;
  const colorClass = isPos ? "text-red-600 dark:text-red-400" : "text-blue-600 dark:text-blue-400";
  const years = item.actual_years_10y;
  const yearLabel = years != null && years < 9.5 ? `*${years.toFixed(1)}년` : "10년";
  return (
    <div className="text-right">
      <div className={`font-medium text-xs ${colorClass}`}>
        {isPos ? "+" : ""}
        {cagr.toFixed(1)}% /yr
      </div>
      <div className="text-xs text-gray-600 dark:text-gray-500">
        ({isPos ? "+" : ""}
        {total.toFixed(0)}%, {yearLabel})
      </div>
    </div>
  );
}

export function CagrCard({ label, cagr }: { label: string; cagr: number | null | undefined }) {
  if (cagr == null) return null;
  const isPos = cagr >= 0;
  return (
    <div className="bg-gray-100 dark:bg-gray-700 rounded-xl p-3 text-center">
      <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</div>
      <div
        className={`text-sm font-semibold ${isPos ? "text-red-600 dark:text-red-400" : "text-blue-600 dark:text-blue-400"}`}
      >
        {isPos ? "+" : ""}
        {cagr.toFixed(1)}% /yr
      </div>
      <div className="text-xs text-gray-600 dark:text-gray-500">10년 CAGR</div>
    </div>
  );
}
