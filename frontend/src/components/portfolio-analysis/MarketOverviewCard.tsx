import type { ExchangeRateInfo, MarketIndexItem, SectorInfo } from "@/api/aiAnalysis";
import { pnlColor } from "@/utils/colors";
import { fmtPct } from "@/utils/format";

interface Props {
  indices: MarketIndexItem[];
  exchangeRate: ExchangeRateInfo | undefined;
  sectors: SectorInfo[];
}

function ChangeCell({ value }: { value: number | null }) {
  if (value == null) return <span className="text-gray-400">—</span>;
  return <span className={pnlColor(value)}>{fmtPct(value)}</span>;
}

export default function MarketOverviewCard({ indices, exchangeRate, sectors }: Props) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-4 space-y-4">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">시장 현황</h3>

      {/* 주요 지수 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {indices.map((idx) => (
          <div
            key={idx.symbol}
            className="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 space-y-1"
          >
            <p className="text-xs text-gray-500 dark:text-gray-400">{idx.name}</p>
            <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">
              {idx.price != null ? idx.price.toLocaleString("ko-KR") : "—"}
            </p>
            <div className="flex items-center gap-2 text-xs">
              <ChangeCell value={idx.change_pct} />
              {idx.week_change_pct != null && (
                <span className="text-gray-400">주간 <ChangeCell value={idx.week_change_pct} /></span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* USD/KRW */}
      {exchangeRate && (
        <div className="flex items-center gap-3 text-sm">
          <span className="text-gray-500 dark:text-gray-400">USD/KRW</span>
          <span className="font-semibold text-gray-800 dark:text-gray-100">
            {exchangeRate.usd_krw != null
              ? `₩${exchangeRate.usd_krw.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}`
              : "—"}
          </span>
          <ChangeCell value={exchangeRate.change_pct} />
        </div>
      )}

      {/* 섹터 성과 */}
      {sectors.length > 0 && (
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">섹터 ETF 주간 성과</p>
          <div className="flex flex-wrap gap-2">
            {sectors.map((s) => (
              <span
                key={s.etf_ticker}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300"
              >
                {s.sector}
                <ChangeCell value={s.change_pct} />
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
