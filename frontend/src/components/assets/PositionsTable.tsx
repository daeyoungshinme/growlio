import { Plus } from "lucide-react";
import type { StockSuggestion } from "@/api/assets";
import { fmtKrwPrice, fmtKrwShort } from "@/utils/format";
import { isOverseasMarket } from "@/constants/markets";
import PriceCell from "@/components/common/PriceCell";
import type { Position } from "@/hooks/usePositionsEditor";
import { PnlCell } from "./PositionHelpers";
import { EditableMobilePositionCard } from "./EditableMobilePositionCard";
import { EditableDesktopPositionRow } from "./EditableDesktopPositionRow";

export type { Position };

interface Props {
  rows: Position[];
  liveRows: Position[];
  readonly: boolean;
  usdRate: number | null;
  suggestions: StockSuggestion[];
  suggestIdx: number | null;
  searchLoading: boolean;
  priceLoadingRows: Set<number>;
  setSuggestIdx: (idx: number | null) => void;
  handleNameChange: (i: number, value: string) => void;
  handleNameBlur: (i: number) => void;
  handleSelectSuggestion: (i: number, s: StockSuggestion) => void;
  setRow: (i: number, patch: Partial<Position>) => void;
  removeRow: (i: number) => void;
  addRow: () => void;
  handleAvgPriceUsd: (i: number, usdVal: string) => void;
  handleCurrentPriceUsd: (i: number, usdVal: string) => void;
}

function ReadonlyMobileCard({ row }: { row: Position }) {
  const overseas = isOverseasMarket(row.market);
  return (
    <div className="py-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-sm text-gray-900 dark:text-gray-50">{row.name || "—"}</p>
          {(row.ticker || row.market !== "KOSPI") && (
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
              {row.ticker}
              {row.ticker && " · "}
              {row.market}
            </p>
          )}
        </div>
        <PnlCell val={row.pnl ?? 0} pct={row.pnl_pct ?? 0} />
      </div>
      <div className="mt-1.5 pt-1.5 border-t border-gray-100 dark:border-gray-800 grid grid-cols-3 gap-x-2">
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">수량</p>
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mt-0.5">
            {row.qty.toLocaleString()}주
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">평단가</p>
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mt-0.5">
            {overseas && row.avg_price_usd
              ? `$${row.avg_price_usd.toFixed(2)}`
              : fmtKrwPrice(row.avg_price ?? 0)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">매입금액</p>
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mt-0.5">
            {fmtKrwShort(row.invested_amount ?? 0)}원
          </p>
        </div>
      </div>
    </div>
  );
}

function ReadonlyDesktopRow({ row }: { row: Position }) {
  const overseas = isOverseasMarket(row.market);
  return (
    <tr className="border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50/50 dark:hover:bg-gray-800/50">
      <td className="py-3 pr-3">
        <p className="font-semibold text-sm text-gray-900 dark:text-gray-50">{row.name || "—"}</p>
        {(row.ticker || row.market !== "KOSPI") && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            {row.ticker}
            {row.ticker && " · "}
            {row.market}
          </p>
        )}
      </td>
      <td className="py-3 pr-3 text-right">
        <span className="text-sm font-medium text-gray-800 dark:text-gray-200">
          {row.qty.toLocaleString()}
        </span>
      </td>
      <td className="py-3 pr-3 text-right">
        <PriceCell krw={row.avg_price} usd={row.avg_price_usd} isOverseas={overseas} />
      </td>
      <td className="py-3 pr-3 text-right text-sm font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap">
        {fmtKrwShort(row.invested_amount ?? 0)}원
      </td>
      <td className="py-3 pr-3 text-right">
        <PriceCell krw={row.current_price} usd={row.current_price_usd} isOverseas={overseas} />
      </td>
      <td className="py-3 pr-3 text-right text-sm font-semibold text-gray-800 dark:text-gray-200 whitespace-nowrap">
        {fmtKrwShort(row.value_amount ?? 0)}원
      </td>
      <td className="py-3 pr-3">
        <PnlCell val={row.pnl ?? 0} pct={row.pnl_pct ?? 0} />
      </td>
      <td className="py-3 w-8" />
    </tr>
  );
}

export function PositionsTable({
  rows,
  liveRows,
  readonly,
  usdRate,
  suggestions,
  suggestIdx,
  searchLoading,
  priceLoadingRows,
  setSuggestIdx,
  handleNameChange,
  handleNameBlur,
  handleSelectSuggestion,
  setRow,
  removeRow,
  addRow,
  handleAvgPriceUsd,
  handleCurrentPriceUsd,
}: Props) {
  const handleMarketChange = (i: number, newMarket: string, currentMarket: string) => {
    const wasOverseas = isOverseasMarket(currentMarket);
    const nowOverseas = isOverseasMarket(newMarket);
    if (wasOverseas !== nowOverseas) {
      setRow(i, { market: newMarket, avg_price: 0, avg_price_usd: null, usd_rate: null });
    } else {
      setRow(i, { market: newMarket });
    }
  };

  const sharedProps = {
    usdRate,
    suggestions,
    suggestIdx,
    searchLoading,
    setSuggestIdx,
    handleNameChange,
    handleNameBlur,
    handleSelectSuggestion,
    setRow,
    removeRow,
    handleAvgPriceUsd,
    handleCurrentPriceUsd,
    handleMarketChange,
  };

  return (
    <>
      {/* ── 모바일 카드 뷰 (sm 미만) ── */}
      <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700">
        {readonly
          ? liveRows.map((row, i) => (
              <ReadonlyMobileCard key={row._rowKey ?? String(i)} row={row} />
            ))
          : liveRows.map((row, i) => (
              <EditableMobilePositionCard
                key={row._rowKey ?? String(i)}
                row={row}
                rawRow={rows[i]}
                index={i}
                priceLoading={priceLoadingRows.has(i)}
                {...sharedProps}
              />
            ))}
      </div>

      {/* ── 데스크탑 테이블 뷰 (sm 이상) ── */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 dark:bg-gray-800 text-xs text-gray-400 dark:text-gray-500 border-b border-gray-200 dark:border-gray-700">
              <th className="text-left py-2.5 pr-3 pl-1 font-medium w-52">종목명</th>
              <th className="text-right py-2.5 pr-3 font-medium w-24">보유수량</th>
              <th className="text-right py-2.5 pr-3 font-medium w-32">평단가</th>
              <th className="text-right py-2.5 pr-3 font-medium">매입금액</th>
              <th className="text-right py-2.5 pr-3 font-medium w-32">현재가</th>
              <th className="text-right py-2.5 pr-3 font-medium">평가금액</th>
              <th className="text-right py-2.5 font-medium">수익률</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {readonly
              ? liveRows.map((row, i) => (
                  <ReadonlyDesktopRow key={row._rowKey ?? String(i)} row={row} />
                ))
              : liveRows.map((row, i) => (
                  <EditableDesktopPositionRow
                    key={row._rowKey ?? String(i)}
                    row={row}
                    rawRow={rows[i]}
                    index={i}
                    priceLoading={priceLoadingRows.has(i)}
                    {...sharedProps}
                  />
                ))}
          </tbody>
        </table>
      </div>

      {!readonly && (
        <button
          onClick={addRow}
          className="mt-3 flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium"
        >
          <Plus size={14} /> 종목 추가
        </button>
      )}
    </>
  );
}
