import { useState, useMemo } from "react";
import { Info, TrendingUp, TrendingDown, Lightbulb, Calculator } from "lucide-react";
import { OverseasPositionDetail } from "../../api/tax";
import { fmtKrw, fmtPct } from "../../utils/format";
import { pnlColor } from "../../utils/colors";

const DEDUCTION = 2_500_000;
const TAX_RATE = 0.22;

interface Props {
  positions: OverseasPositionDetail[];
}

function calcTax(realizedGain: number): number {
  return Math.round(Math.max(0, realizedGain - DEDUCTION) * TAX_RATE);
}

const posKey = (pos: OverseasPositionDetail) => `${pos.account_id}-${pos.ticker}`;

export default function TaxPlannerSection({ positions }: Props) {
  const [alreadyRealizedInput, setAlreadyRealizedInput] = useState("");
  const [sellQtyMap, setSellQtyMap] = useState<Record<string, number>>({});

  const alreadyRealized = useMemo(() => {
    const v = parseFloat(alreadyRealizedInput.replace(/,/g, ""));
    return isNaN(v) ? 0 : v;
  }, [alreadyRealizedInput]);

  const profitPositions = useMemo(
    () => positions.filter((p) => p.unrealized_pnl_krw > 0).sort((a, b) => a.unrealized_pnl_krw - b.unrealized_pnl_krw),
    [positions]
  );
  const lossPositions = useMemo(
    () => positions.filter((p) => p.unrealized_pnl_krw <= 0).sort((a, b) => a.unrealized_pnl_krw - b.unrealized_pnl_krw),
    [positions]
  );

  const totalLoss = useMemo(
    () => lossPositions.reduce((s, p) => s + p.unrealized_pnl_krw, 0),
    [lossPositions]
  );

  const remainingDeduction = Math.max(0, DEDUCTION - alreadyRealized);
  const maxTaxFreeProfit = remainingDeduction + Math.abs(totalLoss);
  const currentTax = calcTax(alreadyRealized);
  const deductionUsedPct = Math.min(100, (Math.max(0, alreadyRealized) / DEDUCTION) * 100);

  const totalSimPnl = useMemo(
    () =>
      [...profitPositions, ...lossPositions].reduce((s, p) => {
        const qty = sellQtyMap[posKey(p)] ?? 0;
        const pnlPs = p.qty > 0 ? p.unrealized_pnl_krw / p.qty : 0;
        return s + pnlPs * qty;
      }, 0),
    [sellQtyMap, profitPositions, lossPositions]
  );

  const hasAnyQtyInput = Object.values(sellQtyMap).some((q) => q > 0);
  const simTotalRealized = alreadyRealized + totalSimPnl;
  const simTax = calcTax(simTotalRealized);
  const simTaxDiff = simTax - currentTax;

  const recommendations = useMemo(() => {
    if (hasAnyQtyInput) return [];
    const recs: { pos: OverseasPositionDetail; label: string; taxSaved: number }[] = [];
    let budget = maxTaxFreeProfit;
    for (const pos of profitPositions) {
      if (pos.unrealized_pnl_krw <= budget) {
        recs.push({
          pos,
          label: `전량(${pos.qty.toLocaleString()}주) 매도`,
          taxSaved: Math.round(pos.unrealized_pnl_krw * TAX_RATE),
        });
        budget -= pos.unrealized_pnl_krw;
      } else if (budget > 0 && pos.qty > 0) {
        const pnlPerShare = pos.unrealized_pnl_krw / pos.qty;
        if (pnlPerShare > 0) {
          const shares = Math.floor(budget / pnlPerShare);
          if (shares > 0) {
            recs.push({
              pos,
              label: `${shares.toLocaleString()}주 매도`,
              taxSaved: Math.round(shares * pnlPerShare * TAX_RATE),
            });
          }
        }
        break;
      }
    }
    return recs;
  }, [hasAnyQtyInput, profitPositions, maxTaxFreeProfit]);

  const handleQtyChange = (pos: OverseasPositionDetail, value: string) => {
    const n = Math.max(0, Math.min(pos.qty, parseInt(value) || 0));
    setSellQtyMap((prev) => ({ ...prev, [posKey(pos)]: n }));
  };

  if (positions.length === 0) {
    return (
      <div className="mt-4 rounded-xl bg-gray-50 dark:bg-gray-800/50 p-4 text-center text-sm text-gray-400 dark:text-gray-500">
        해외 종목 보유 현황이 없습니다.
      </div>
    );
  }

  return (
    <div className="mt-4 space-y-4">
      <div className="flex items-center gap-2">
        <Lightbulb size={15} className="text-amber-500 shrink-0" />
        <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">해외 양도세 절세 플래너</span>
        <span className="text-xs text-gray-400 dark:text-gray-500">250만원 공제 최대 활용</span>
      </div>

      {/* 올해 이미 실현한 손익 입력 + 공제 현황 */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-3">
        {/* 배당금 안내 */}
        <div className="flex items-start gap-2 p-2.5 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
          <Info size={13} className="text-blue-500 mt-0.5 shrink-0" />
          <p className="text-xs text-blue-700 dark:text-blue-300 leading-relaxed">
            <span className="font-medium">배당금은 250만원 공제 대상이 아닙니다.</span>{" "}
            배당금은 배당소득세(15.4%)로 별도 원천징수됩니다. 이 플래너는 해외 주식
            <span className="font-medium"> 매매 차익(양도소득)</span>만 계산합니다.
            단, 배당금 + 양도차익 합계가 연 2,000만원 초과 시 금융소득 종합과세 대상이 될 수 있습니다.
          </p>
        </div>

        <div className="flex items-start gap-2">
          <Info size={13} className="text-gray-400 mt-0.5 shrink-0" />
          <p className="text-xs text-gray-500 dark:text-gray-400">
            올해 이미 해외 주식을 매도해 실현한 손익이 있다면 입력하세요 (양도차익만, 배당금 제외). 없으면 0.
          </p>
        </div>

        {/* 실현 손익 입력 — 모바일에서 wrap 허용 */}
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 shrink-0">
            올해 실현 손익 (원)
          </label>
          <input
            type="text"
            inputMode="numeric"
            value={alreadyRealizedInput}
            onChange={(e) => setAlreadyRealizedInput(e.target.value)}
            placeholder="0"
            className="w-36 min-w-0 border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {alreadyRealized !== 0 && (
            <span className={`text-xs font-medium ${pnlColor(alreadyRealized)}`}>
              {fmtKrw(alreadyRealized)}
            </span>
          )}
        </div>

        {/* 공제 현황 */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500 dark:text-gray-400">공제 사용 현황</span>
            <span className="font-medium text-gray-700 dark:text-gray-300">
              {fmtKrw(Math.max(0, alreadyRealized))} / {fmtKrw(DEDUCTION)}
            </span>
          </div>
          <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                deductionUsedPct >= 100
                  ? "bg-red-400"
                  : deductionUsedPct >= 70
                  ? "bg-amber-400"
                  : "bg-emerald-400"
              }`}
              style={{ width: `${deductionUsedPct}%` }}
            />
          </div>
          <div className="flex flex-wrap items-start justify-between gap-y-1">
            <div className="flex-1 min-w-0">
              {alreadyRealized < DEDUCTION ? (
                <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                  공제 잔여 {fmtKrw(remainingDeduction)} — 세금 없이 이만큼 더 수익 실현 가능
                </span>
              ) : (
                <span className="text-xs text-red-500 dark:text-red-400 font-medium">
                  공제 초과 — 초과분에 22% 과세 (현재 예상세금 {fmtKrw(currentTax)})
                </span>
              )}
            </div>
            {totalLoss < 0 && (
              <span className="text-xs text-blue-500 dark:text-blue-400 shrink-0">
                손실 통산 시 {fmtKrw(maxTaxFreeProfit)}까지 무세 실현
              </span>
            )}
          </div>
        </div>
      </div>

      {/* 수익 종목 */}
      {profitPositions.length > 0 && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 dark:border-gray-800">
            <TrendingUp size={14} className="text-red-400" />
            <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">수익 종목</span>
            <span className="hidden sm:inline ml-1 text-xs text-gray-400 dark:text-gray-500">— 매도 수량을 입력해 세금을 계산하세요</span>
            <span className="ml-auto text-xs text-gray-400 dark:text-gray-500">{profitPositions.length}종목</span>
          </div>

          {/* 모바일: 카드 레이아웃 */}
          <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-800">
            {profitPositions.map((pos) => {
              const qty = sellQtyMap[posKey(pos)] ?? 0;
              const pnlPs = pos.qty > 0 ? pos.unrealized_pnl_krw / pos.qty : 0;
              const rowSimPnl = pnlPs * qty;
              const isWithinBudget = pos.unrealized_pnl_krw <= maxTaxFreeProfit;
              return (
                <div key={posKey(pos)} className="px-4 py-2 space-y-1.5">
                  {/* 행1: ticker + 회사명 | 수익률 */}
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
                  {/* 행2: PnL | 매도 수량 입력 */}
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-sm font-medium ${pnlColor(pos.unrealized_pnl_krw)}`}>
                      {fmtKrw(pos.unrealized_pnl_krw)}
                      {qty > 0 && (
                        <span className={`ml-1.5 text-xs ${pnlColor(rowSimPnl)}`}>
                          ({qty}주: {fmtKrw(rowSimPnl)})
                        </span>
                      )}
                    </span>
                    <div className="flex items-center gap-1 shrink-0">
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
                      <span className="text-xs text-gray-400 dark:text-gray-500">/ {Math.floor(pos.qty)}주</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* 데스크탑: 테이블 레이아웃 */}
          <div className="hidden sm:block overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-800">
                  <th className="px-2 py-2 sm:px-4 text-left font-medium">종목</th>
                  <th className="px-2 py-2 sm:px-4 text-right font-medium">미실현 수익</th>
                  <th className="px-2 py-2 sm:px-4 text-right font-medium">수익률</th>
                  <th className="px-2 py-2 sm:px-4 text-right font-medium">매도 수량</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
                {profitPositions.map((pos) => {
                  const qty = sellQtyMap[posKey(pos)] ?? 0;
                  const pnlPs = pos.qty > 0 ? pos.unrealized_pnl_krw / pos.qty : 0;
                  const rowSimPnl = pnlPs * qty;
                  const isWithinBudget = pos.unrealized_pnl_krw <= maxTaxFreeProfit;
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
                        <div className="flex items-center justify-end gap-1">
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
                          <span className="text-gray-400 dark:text-gray-500 whitespace-nowrap">
                            / {Math.floor(pos.qty)}주
                          </span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 손실 종목 */}
      {lossPositions.length > 0 && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 dark:border-gray-800">
            <TrendingDown size={14} className="text-blue-400" />
            <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">손실 종목</span>
            <span className="hidden sm:inline text-xs text-gray-400 dark:text-gray-500 ml-1">
              — 매도 시 손익 통산으로 수익 종목 절세 효과
            </span>
            <span className="ml-auto text-xs text-gray-400 dark:text-gray-500">{lossPositions.length}종목</span>
          </div>

          {/* 모바일: 카드 레이아웃 */}
          <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-800">
            {lossPositions.map((pos) => {
              const qty = sellQtyMap[posKey(pos)] ?? 0;
              const pnlPs = pos.qty > 0 ? pos.unrealized_pnl_krw / pos.qty : 0;
              const rowSimPnl = pnlPs * qty;
              const taxSaved = Math.round(Math.abs(rowSimPnl) * TAX_RATE);
              return (
                <div key={posKey(pos)} className="px-4 py-2 space-y-1.5">
                  {/* 행1: ticker + 회사명 | 손실률 */}
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1 min-w-0">
                      <span className="font-medium text-sm text-gray-800 dark:text-gray-200">{pos.ticker}</span>
                      <span className="text-gray-400 dark:text-gray-500 text-xs">{pos.market}</span>
                      <span className="text-gray-400 dark:text-gray-500 text-xs truncate">· {pos.name}</span>
                    </div>
                    <span className={`text-sm font-medium shrink-0 ${pnlColor(pos.unrealized_pnl_pct)}`}>
                      {fmtPct(pos.unrealized_pnl_pct)}
                    </span>
                  </div>
                  {/* 행2: PnL | 매도 수량 입력 */}
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
                        <span className="text-xs text-gray-400 dark:text-gray-500">/ {Math.floor(pos.qty)}주</span>
                      </div>
                      {qty > 0 && (
                        <div className="text-xs text-blue-500 dark:text-blue-400 font-medium mt-0.5">
                          최대 {fmtKrw(taxSaved)} 절세
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
            {totalLoss < 0 && !hasAnyQtyInput && (
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
                  <th className="px-2 py-2 sm:px-4 text-right font-medium">미실현 손실</th>
                  <th className="px-2 py-2 sm:px-4 text-right font-medium">손실률</th>
                  <th className="px-2 py-2 sm:px-4 text-right font-medium">매도 수량</th>
                  <th className="px-2 py-2 sm:px-4 text-right font-medium">통산 절세 효과</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
                {lossPositions.map((pos) => {
                  const qty = sellQtyMap[posKey(pos)] ?? 0;
                  const pnlPs = pos.qty > 0 ? pos.unrealized_pnl_krw / pos.qty : 0;
                  const rowSimPnl = pnlPs * qty;
                  const taxSaved = Math.round(Math.abs(rowSimPnl) * TAX_RATE);
                  return (
                    <tr key={posKey(pos)} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                      <td className="px-2 py-2.5 sm:px-4">
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-gray-800 dark:text-gray-200">{pos.ticker}</span>
                          <span className="text-gray-400 dark:text-gray-500 text-xs">{pos.market}</span>
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
                        <div className="flex items-center justify-end gap-1">
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
                          <span className="text-gray-400 dark:text-gray-500 whitespace-nowrap">
                            / {Math.floor(pos.qty)}주
                          </span>
                        </div>
                      </td>
                      <td className="px-2 py-2.5 sm:px-4 text-right">
                        {qty === 0 ? (
                          <span className="text-gray-300 dark:text-gray-600">—</span>
                        ) : (
                          <span className="text-blue-500 dark:text-blue-400 font-medium">
                            최대 {fmtKrw(taxSaved)} 절세
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              {totalLoss < 0 && !hasAnyQtyInput && (
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
        </div>
      )}

      {/* 시뮬레이션 합계 카드 (수량 입력 시 표시) */}
      {hasAnyQtyInput && (
        <div className={`rounded-xl border p-3 sm:p-4 space-y-3 ${
          simTax === 0
            ? "border-emerald-200 dark:border-emerald-800/50 bg-emerald-50 dark:bg-emerald-900/20"
            : "border-orange-200 dark:border-orange-800/50 bg-orange-50 dark:bg-orange-900/20"
        }`}>
          <div className="flex items-center gap-2">
            <Calculator size={13} className={simTax === 0 ? "text-emerald-500" : "text-orange-500"} />
            <span className={`text-xs font-semibold ${simTax === 0 ? "text-emerald-700 dark:text-emerald-400" : "text-orange-700 dark:text-orange-400"}`}>
              매도 시뮬레이션 합계
            </span>
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-2 sm:gap-x-6 sm:gap-y-1.5 text-xs">
            <span className="text-gray-500 dark:text-gray-400">선택 종목 실현 손익</span>
            <span className={`text-right font-medium ${pnlColor(totalSimPnl)}`}>{fmtKrw(totalSimPnl)}</span>
            {alreadyRealized !== 0 && (
              <>
                <span className="text-gray-500 dark:text-gray-400">기존 실현 손익</span>
                <span className={`text-right font-medium ${pnlColor(alreadyRealized)}`}>{fmtKrw(alreadyRealized)}</span>
              </>
            )}
            <span className="text-gray-500 dark:text-gray-400">통산 실현 손익</span>
            <span className={`text-right font-medium ${pnlColor(simTotalRealized)}`}>{fmtKrw(simTotalRealized)}</span>
            <span className="text-gray-500 dark:text-gray-400">250만원 공제</span>
            <span className="text-right text-gray-600 dark:text-gray-300">−{fmtKrw(Math.min(DEDUCTION, Math.max(0, simTotalRealized)))}</span>
            <span className={`font-semibold ${simTax === 0 ? "text-emerald-600 dark:text-emerald-400" : "text-orange-600 dark:text-orange-400"}`}>
              예상 납부 세금
            </span>
            <span className={`text-right font-bold text-base ${simTax === 0 ? "text-emerald-600 dark:text-emerald-400" : "text-orange-600 dark:text-orange-400"}`}>
              {fmtKrw(simTax)}
            </span>
            {simTaxDiff !== 0 && currentTax > 0 && (
              <>
                <span className="text-gray-400 dark:text-gray-500">기존 대비 세금 변화</span>
                <span className={`text-right font-medium ${pnlColor(-simTaxDiff)}`}>
                  {simTaxDiff > 0 ? "+" : ""}{fmtKrw(simTaxDiff)}
                </span>
              </>
            )}
          </div>
          <p className="text-xs text-gray-400 dark:text-gray-500">
            * 미실현 손익 기준 추정치. 22% 세율(지방소득세 포함). 실제 매도가는 다를 수 있습니다.
          </p>
        </div>
      )}

      {/* 절세 추천 (수량 미입력 시에만 표시) */}
      {!hasAnyQtyInput && recommendations.length > 0 && (
        <div className="rounded-xl border border-amber-200 dark:border-amber-800/50 bg-amber-50 dark:bg-amber-900/20 p-4 space-y-2">
          <div className="flex items-center gap-2">
            <Lightbulb size={13} className="text-amber-500 shrink-0" />
            <span className="text-xs font-semibold text-amber-700 dark:text-amber-400">
              절세 추천 — 세금 없이 실현 가능한 종목
            </span>
          </div>
          <ul className="space-y-1.5">
            {recommendations.map(({ pos, label, taxSaved }) => (
              <li key={`rec-${posKey(pos)}`} className="flex flex-wrap items-start justify-between gap-y-1 text-xs">
                <span className="flex-1 min-w-0 text-gray-700 dark:text-gray-300">
                  <span className="font-medium">{pos.ticker}</span>{" "}
                  <span className="text-gray-500 dark:text-gray-400">{label}</span>
                  {" → "}수익 {fmtKrw(pos.unrealized_pnl_krw)} 실현
                </span>
                <span className="text-emerald-600 dark:text-emerald-400 font-medium ml-2 shrink-0">
                  세금 절감 {fmtKrw(taxSaved)}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-amber-600 dark:text-amber-500 mt-1">
            * 수익 종목 테이블에서 매도 수량을 직접 입력하면 자세한 시뮬레이션을 확인할 수 있습니다.
          </p>
        </div>
      )}

      {profitPositions.length === 0 && lossPositions.length === 0 && (
        <div className="rounded-xl bg-gray-50 dark:bg-gray-800/50 p-4 text-center text-xs text-gray-400 dark:text-gray-500">
          해외 종목 미실현 손익 정보가 없습니다.
        </div>
      )}
    </div>
  );
}
