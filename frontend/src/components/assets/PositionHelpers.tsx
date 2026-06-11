import { fmtKrwShort } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { POSITION_MARKETS } from "@/constants/markets";
import type { StockSuggestion } from "@/api/assets";
import type { Position } from "@/hooks/usePositionsEditor";

export function PnlCell({ val, pct }: { val: number; pct: number }) {
  const color = pnlColor(val);
  return (
    <div className="text-right text-xs">
      <div className={`font-bold ${color}`}>{pct >= 0 ? "+" : ""}{pct.toFixed(2)}%</div>
      <div className={color}>{val >= 0 ? "+" : ""}{fmtKrwShort(val)}원</div>
    </div>
  );
}

export function MarketSelect({ value, disabled, onChange }: {
  value: string;
  disabled: boolean;
  onChange: (market: string) => void;
}) {
  return (
    <select
      className="text-xs text-gray-400 dark:text-gray-500 border-0 bg-transparent p-0 cursor-pointer focus:outline-none"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {POSITION_MARKETS.map((m) => <option key={m} value={m}>{m}</option>)}
    </select>
  );
}

export interface EditablePositionRowProps {
  row: Position;
  rawRow: Position;
  index: number;
  usdRate: number | null;
  priceLoading: boolean;
  suggestions: StockSuggestion[];
  suggestIdx: number | null;
  searchLoading: boolean;
  setSuggestIdx: (idx: number | null) => void;
  handleNameChange: (i: number, value: string) => void;
  handleNameBlur: (i: number) => void;
  handleSelectSuggestion: (i: number, s: StockSuggestion) => void;
  setRow: (i: number, patch: Partial<Position>) => void;
  removeRow: (i: number) => void;
  handleAvgPriceUsd: (i: number, usdVal: string) => void;
  handleCurrentPriceUsd: (i: number, usdVal: string) => void;
  handleMarketChange: (i: number, newMarket: string, currentMarket: string) => void;
}
