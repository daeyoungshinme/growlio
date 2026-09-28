import { useState, useMemo } from "react";
import { OverseasPositionDetail } from "@/api/tax";

/** 해외 양도세 기본공제·세율 — 세법 원천은 백엔드(`tax_service` 연도별 테이블)이고, 화면은
 * `/tax/summary` 응답(`overseas_gain_deduction_krw`, `rates.overseas_tax_rate_pct`)을 넘겨받아 쓴다.
 * 아래 값은 응답이 없을 때의 폴백이다. */
export const TAX_DEDUCTION = 2_500_000;
export const TAX_RATE = 0.22;

export interface OverseasTaxRule {
  deduction: number;
  rate: number;
}

export const DEFAULT_OVERSEAS_TAX_RULE: OverseasTaxRule = {
  deduction: TAX_DEDUCTION,
  rate: TAX_RATE,
};

export function posKey(pos: OverseasPositionDetail): string {
  return `${pos.account_id}-${pos.ticker}`;
}

function calcTax(realizedGain: number, rule: OverseasTaxRule): number {
  return Math.round(Math.max(0, realizedGain - rule.deduction) * rule.rate);
}

/**
 * @param autoRealized 증권사 체결 기준 자동 집계된 올해 실현손익(없으면 null) — 사용자가 직접 입력하기 전까지 기본값
 * @param rule 백엔드 세금 요약의 공제·세율 (없으면 폴백 상수)
 */
export function useTaxSimulation(
  positions: OverseasPositionDetail[],
  autoRealized: number | null = null,
  rule: OverseasTaxRule = DEFAULT_OVERSEAS_TAX_RULE,
) {
  const { deduction: taxDeduction, rate: taxRate } = rule;
  const [alreadyRealizedInput, setAlreadyRealizedInput] = useState("");
  const [sellQtyMap, setSellQtyMap] = useState<Record<string, number>>({});

  const isManualRealized = alreadyRealizedInput.trim() !== "";
  const alreadyRealized = useMemo(() => {
    if (!isManualRealized) return autoRealized ?? 0;
    const v = parseFloat(alreadyRealizedInput.replace(/,/g, ""));
    return isNaN(v) ? 0 : v;
  }, [alreadyRealizedInput, isManualRealized, autoRealized]);

  const profitPositions = useMemo(
    () =>
      positions
        .filter((p) => p.unrealized_pnl_krw > 0)
        .sort((a, b) => a.unrealized_pnl_krw - b.unrealized_pnl_krw),
    [positions],
  );

  const lossPositions = useMemo(
    () =>
      positions
        .filter((p) => p.unrealized_pnl_krw <= 0)
        .sort((a, b) => a.unrealized_pnl_krw - b.unrealized_pnl_krw),
    [positions],
  );

  const totalLoss = useMemo(
    () => lossPositions.reduce((s, p) => s + p.unrealized_pnl_krw, 0),
    [lossPositions],
  );

  const remainingDeduction = Math.max(0, taxDeduction - alreadyRealized);
  const maxTaxFreeProfit = remainingDeduction + Math.abs(totalLoss);
  const currentTax = calcTax(alreadyRealized, rule);
  const deductionUsedPct =
    taxDeduction > 0 ? Math.min(100, (Math.max(0, alreadyRealized) / taxDeduction) * 100) : 100;

  const totalSimPnl = useMemo(
    () =>
      [...profitPositions, ...lossPositions].reduce((s, p) => {
        const qty = sellQtyMap[posKey(p)] ?? 0;
        const pnlPs = p.qty > 0 ? p.unrealized_pnl_krw / p.qty : 0;
        return s + pnlPs * qty;
      }, 0),
    [sellQtyMap, profitPositions, lossPositions],
  );

  const hasAnyQtyInput = Object.values(sellQtyMap).some((q) => q > 0);
  const simTotalRealized = alreadyRealized + totalSimPnl;
  const simTax = calcTax(simTotalRealized, rule);
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
          taxSaved: Math.round(pos.unrealized_pnl_krw * taxRate),
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
              taxSaved: Math.round(shares * pnlPerShare * taxRate),
            });
          }
        }
        break;
      }
    }
    return recs;
  }, [hasAnyQtyInput, profitPositions, maxTaxFreeProfit, taxRate]);

  const handleQtyChange = (pos: OverseasPositionDetail, value: string) => {
    const n = Math.max(0, Math.min(pos.qty, parseInt(value) || 0));
    setSellQtyMap((prev) => ({ ...prev, [posKey(pos)]: n }));
  };

  return {
    taxDeduction,
    taxRate,
    alreadyRealizedInput,
    setAlreadyRealizedInput,
    sellQtyMap,
    alreadyRealized,
    isManualRealized,
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
