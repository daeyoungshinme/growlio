import { useState, useMemo } from "react";
import { OverseasPositionDetail } from "@/api/tax";

export const TAX_DEDUCTION = 2_500_000;
export const TAX_RATE = 0.22;

export function posKey(pos: OverseasPositionDetail): string {
  return `${pos.account_id}-${pos.ticker}`;
}

function calcTax(realizedGain: number): number {
  return Math.round(Math.max(0, realizedGain - TAX_DEDUCTION) * TAX_RATE);
}

export function useTaxSimulation(positions: OverseasPositionDetail[]) {
  const [alreadyRealizedInput, setAlreadyRealizedInput] = useState("");
  const [sellQtyMap, setSellQtyMap] = useState<Record<string, number>>({});

  const alreadyRealized = useMemo(() => {
    const v = parseFloat(alreadyRealizedInput.replace(/,/g, ""));
    return isNaN(v) ? 0 : v;
  }, [alreadyRealizedInput]);

  const profitPositions = useMemo(
    () =>
      positions
        .filter((p) => p.unrealized_pnl_krw > 0)
        .sort((a, b) => a.unrealized_pnl_krw - b.unrealized_pnl_krw),
    [positions]
  );

  const lossPositions = useMemo(
    () =>
      positions
        .filter((p) => p.unrealized_pnl_krw <= 0)
        .sort((a, b) => a.unrealized_pnl_krw - b.unrealized_pnl_krw),
    [positions]
  );

  const totalLoss = useMemo(
    () => lossPositions.reduce((s, p) => s + p.unrealized_pnl_krw, 0),
    [lossPositions]
  );

  const remainingDeduction = Math.max(0, TAX_DEDUCTION - alreadyRealized);
  const maxTaxFreeProfit = remainingDeduction + Math.abs(totalLoss);
  const currentTax = calcTax(alreadyRealized);
  const deductionUsedPct = Math.min(100, (Math.max(0, alreadyRealized) / TAX_DEDUCTION) * 100);

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

  return {
    alreadyRealizedInput,
    setAlreadyRealizedInput,
    sellQtyMap,
    alreadyRealized,
    profitPositions,
    lossPositions,
    totalLoss,
    remainingDeduction,
    maxTaxFreeProfit,
    currentTax,
    deductionUsedPct,
    totalSimPnl,
    hasAnyQtyInput,
    simTotalRealized,
    simTax,
    simTaxDiff,
    recommendations,
    handleQtyChange,
  };
}
