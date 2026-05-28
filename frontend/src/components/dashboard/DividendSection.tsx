import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { TickerDividendItem } from "../../api/dashboard";
import DividendByTickerTable from "./DividendByTickerTable";
import { fmtKrw } from "../../utils/format";

interface Props {
  annualReceived: number | null;
  estimatedAnnual: number | null;
  tickerItems?: TickerDividendItem[];
  tickerItemsLoading?: boolean;
}

function StatBox({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 flex-1">
      <p className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide">{label}</p>
      <p className="text-base font-semibold text-gray-900 dark:text-gray-50 mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function DividendSection({ annualReceived, estimatedAnnual, tickerItems, tickerItemsLoading }: Props) {
  const [showTicker, setShowTicker] = useState(false);
  const filteredTickerItems = (tickerItems ?? [])
    .filter((d) => d.estimated_annual_krw > 0)
    .sort((a, b) => b.estimated_annual_krw - a.estimated_annual_krw);

  return (
    <div className="space-y-3">
      <div className="flex gap-3">
        <StatBox
          label="올해 배당금"
          value={annualReceived != null && annualReceived > 0 ? fmtKrw(annualReceived) : "—"}
          sub={annualReceived != null && annualReceived > 0 ? "실수령 합계" : "배당 내역을 입력해주세요"}
        />
        <StatBox
          label="예상 배당금"
          value={estimatedAnnual != null && estimatedAnnual > 0 ? fmtKrw(estimatedAnnual) : "—"}
          sub="배당수익률 기준 추정"
        />
      </div>

      <div>
        <button
          onClick={() => setShowTicker((v) => !v)}
          className="flex items-center justify-between w-full text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 font-medium transition-colors"
        >
          <span>
            종목별 배당 현황
            {!showTicker && filteredTickerItems.length > 0 && (
              <span className="ml-1 text-gray-300 dark:text-gray-600">({filteredTickerItems.length}개 종목)</span>
            )}
          </span>
          <ChevronDown
            size={14}
            className={`transition-transform duration-200 ${showTicker ? "rotate-180" : ""}`}
          />
        </button>
        {showTicker && (
          <div className="mt-2">
            <DividendByTickerTable
              items={filteredTickerItems}
              isLoading={tickerItemsLoading ?? false}
            />
          </div>
        )}
      </div>
    </div>
  );
}
