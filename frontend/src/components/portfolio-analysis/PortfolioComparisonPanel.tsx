import { ArrowRight } from "lucide-react";
import type { RebalancingAnalysis, RebalancingItem } from "@/api/rebalancing";
import { fmtKrwNullable, fmtPct } from "@/utils/format";

interface Props {
  accountName: string;
  currentAnalysis: RebalancingAnalysis;
  proposedAnalysis: RebalancingAnalysis;
  onReplace: () => void;
  onCancel: () => void;
}

interface MergedRow {
  ticker: string;
  name: string;
  market: string;
  currentWeight: number;
  targetAWeight: number;
  targetBWeight: number;
  diffAKrw: number;
  diffBKrw: number;
}

function buildMergedRows(a: RebalancingAnalysis, b: RebalancingAnalysis): MergedRow[] {
  const mapA = new Map<string, RebalancingItem>();
  const mapB = new Map<string, RebalancingItem>();
  for (const item of a.items) mapA.set(`${item.ticker}:${item.market}`, item);
  for (const item of b.items) mapB.set(`${item.ticker}:${item.market}`, item);

  const allKeys = new Set([...mapA.keys(), ...mapB.keys()]);
  const rows: MergedRow[] = [];

  for (const key of allKeys) {
    const ia = mapA.get(key);
    const ib = mapB.get(key);
    const ref = ia ?? ib!;
    rows.push({
      ticker: ref.ticker,
      name: ref.name,
      market: ref.market,
      currentWeight: ia?.current_weight_pct ?? ib?.current_weight_pct ?? 0,
      targetAWeight: ia?.target_weight_pct ?? 0,
      targetBWeight: ib?.target_weight_pct ?? 0,
      diffAKrw: ia?.diff_krw ?? 0,
      diffBKrw: ib?.diff_krw ?? 0,
    });
  }

  return rows.sort((x, y) => Math.max(y.targetAWeight, y.targetBWeight) - Math.max(x.targetAWeight, x.targetBWeight));
}

function DiffBadge({ value }: { value: number }) {
  if (Math.abs(value) < 1000) return <span className="text-gray-400 dark:text-gray-500">—</span>;
  const positive = value > 0;
  return (
    <span className={positive ? "text-red-500" : "text-blue-500"}>
      {positive ? "+" : ""}{fmtKrwNullable(value)}
    </span>
  );
}

export default function PortfolioComparisonPanel({
  accountName,
  currentAnalysis,
  proposedAnalysis,
  onReplace,
  onCancel,
}: Props) {
  const rows = buildMergedRows(currentAnalysis, proposedAnalysis);

  const cagrA = currentAnalysis.target_weighted_cagr_10y_pct;
  const cagrB = proposedAnalysis.target_weighted_cagr_10y_pct;
  const divA = currentAnalysis.target_portfolio_annual_dividend;
  const divB = proposedAnalysis.target_portfolio_annual_dividend;
  const baseA = currentAnalysis.base_value_krw;
  const baseB = proposedAnalysis.base_value_krw;
  const divYieldA = baseA > 0 ? (divA / baseA) * 100 : null;
  const divYieldB = baseB > 0 ? (divB / baseB) * 100 : null;

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded-lg truncate max-w-[140px]">
          {currentAnalysis.portfolio_name}
        </span>
        <ArrowRight size={14} className="text-gray-400 flex-shrink-0" />
        <span className="text-xs font-medium text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950 px-2 py-1 rounded-lg truncate max-w-[140px]">
          {proposedAnalysis.portfolio_name}
        </span>
        <span className="text-xs text-gray-400 dark:text-gray-500">({accountName})</span>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 p-3 space-y-2">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400">기대 CAGR (10y)</p>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-600 dark:text-gray-300">{cagrA != null ? fmtPct(cagrA) : "—"}</span>
            <ArrowRight size={12} className="text-gray-400" />
            <span className={`font-semibold ${cagrB != null && cagrA != null && cagrB > cagrA ? "text-red-500" : "text-blue-500"}`}>
              {cagrB != null ? fmtPct(cagrB) : "—"}
            </span>
          </div>
        </div>
        <div className="rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 p-3 space-y-2">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400">예상 배당수익률</p>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-600 dark:text-gray-300">{divYieldA != null ? fmtPct(divYieldA) : "—"}</span>
            <ArrowRight size={12} className="text-gray-400" />
            <span className={`font-semibold ${divYieldB != null && divYieldA != null && divYieldB > divYieldA ? "text-red-500" : "text-blue-500"}`}>
              {divYieldB != null ? fmtPct(divYieldB) : "—"}
            </span>
          </div>
        </div>
      </div>

      {/* 비교 테이블 */}
      <div className="overflow-x-auto rounded-xl border border-gray-100 dark:border-gray-800">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900">
              <th className="text-left py-2.5 px-3 font-medium text-gray-500 dark:text-gray-400">종목</th>
              <th className="text-right py-2.5 px-3 font-medium text-gray-500 dark:text-gray-400">현재</th>
              <th className="text-right py-2.5 px-3 font-medium text-gray-500 dark:text-gray-400">기존 목표</th>
              <th className="text-right py-2.5 px-3 font-medium text-blue-600 dark:text-blue-400">새 목표</th>
              <th className="text-right py-2.5 px-3 font-medium text-gray-500 dark:text-gray-400">기존 매매</th>
              <th className="text-right py-2.5 px-3 font-medium text-blue-600 dark:text-blue-400">새 매매</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
            {rows.map((row) => (
              <tr key={`${row.ticker}:${row.market}`} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="py-2 px-3">
                  <span className="font-medium text-gray-800 dark:text-gray-200">{row.ticker}</span>
                  <span className="text-gray-400 dark:text-gray-500 ml-1 hidden sm:inline">{row.market}</span>
                </td>
                <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-300">
                  {fmtPct(row.currentWeight)}
                </td>
                <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-300">
                  {row.targetAWeight > 0 ? fmtPct(row.targetAWeight) : <span className="text-gray-300 dark:text-gray-600">—</span>}
                </td>
                <td className="py-2 px-3 text-right font-medium text-blue-700 dark:text-blue-300">
                  {row.targetBWeight > 0 ? fmtPct(row.targetBWeight) : <span className="text-gray-300 dark:text-gray-600">—</span>}
                </td>
                <td className="py-2 px-3 text-right">
                  <DiffBadge value={row.diffAKrw} />
                </td>
                <td className="py-2 px-3 text-right">
                  <DiffBadge value={row.diffBKrw} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 액션 버튼 */}
      <div className="flex gap-2 pt-1">
        <button
          onClick={onCancel}
          className="flex-1 py-2 text-sm border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          현재 목표 유지
        </button>
        <button
          onClick={onReplace}
          className="flex-1 py-2 text-sm bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors"
        >
          새 포트폴리오로 교체
        </button>
      </div>
    </div>
  );
}
