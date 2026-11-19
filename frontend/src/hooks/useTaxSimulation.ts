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

const DEFAULT_OVERSEAS_TAX_RULE: OverseasTaxRule = {
  deduction: TAX_DEDUCTION,
  rate: TAX_RATE,
};

export function posKey(pos: OverseasPositionDetail): string {
  return `${pos.account_id}-${pos.ticker}`;
}

function calcTax(realizedGain: number, rule: OverseasTaxRule): number {
  return Math.round(Math.max(0, realizedGain - rule.deduction) * rule.rate);
}

/** 절세 추천 한 줄 — PROFIT은 세금 없이 실현할 수익 매도, LOSS는 그 무세 실현에 필요한 손실 매도(손익 통산) */
export interface TaxRecommendation {
  pos: OverseasPositionDetail;
  kind: "PROFIT" | "LOSS";
  shares: number;
  /** 이 행을 실행하면 실제로 실현되는 손익(부분 매도면 그 주수만큼) — LOSS는 음수 */
  realizedKrw: number;
  label: string;
  /** PROFIT: 공제·통산이 없었다면 이 실현분에 낼 세금. LOSS: 0(통산 효과는 PROFIT 행에 이미 포함) */
  taxSaved: number;
}

function sellLabel(pos: OverseasPositionDetail, shares: number): string {
  return shares >= pos.qty
    ? `전량(${pos.qty.toLocaleString()}주) 매도`
    : `${shares.toLocaleString()}주 매도`;
}

/**
 * 세금 0원으로 실현할 수 있는 매도 묶음.
 * 1) 올해 남은 공제(`remainingDeduction` — 이미 실현한 손익 반영)만큼 수익 작은 종목부터 채우고,
 * 2) 그 이상은 손실 종목 매도로 통산해야만 무세이므로, 필요한 손실 매도를 **함께 추천 목록에 넣는다**.
 *    `lossPositions`를 빈 배열로 넘기면 손실 매도 없는(공제 잔여만 쓰는) 추천이 된다.
 * 예전엔 미실현 손실 전체를 예산에 더하고 손실 매도는 빼고 보여줘서, 공제를 거의 다 쓴 해에도 큰 수익 실현을
 * "세금 없이"로 추천했다(따라 하면 과세).
 */
export function buildTaxRecommendations(
  profitPositions: OverseasPositionDetail[],
  lossPositions: OverseasPositionDetail[],
  remainingDeduction: number,
  taxRate: number,
): TaxRecommendation[] {
  const profitRecs: TaxRecommendation[] = [];
  const lossQueue = lossPositions
    .filter((p) => p.unrealized_pnl_krw < 0 && p.qty > 0)
    .sort((a, b) => a.unrealized_pnl_krw - b.unrealized_pnl_krw);
  const lossSharesUsed = lossQueue.map(() => 0);
  let lossIdx = 0;
  let budget = Math.max(0, remainingDeduction);

  for (const pos of profitPositions) {
    if (pos.qty <= 0 || pos.unrealized_pnl_krw <= 0) continue;
    const pnlPerShare = pos.unrealized_pnl_krw / pos.qty;

    // 이 종목 전량에 예산이 모자라면 손실 종목을 필요한 주수만큼 끌어온다
    while (budget < pos.unrealized_pnl_krw && lossIdx < lossQueue.length) {
      const loss = lossQueue[lossIdx]!;
      const lossPerShare = Math.abs(loss.unrealized_pnl_krw) / loss.qty;
      const available = loss.qty - lossSharesUsed[lossIdx]!;
      const take = Math.min(available, Math.ceil((pos.unrealized_pnl_krw - budget) / lossPerShare));
      lossSharesUsed[lossIdx] = lossSharesUsed[lossIdx]! + take;
      budget += take * lossPerShare;
      if (lossSharesUsed[lossIdx]! >= loss.qty) lossIdx += 1;
    }

    const shares = pos.unrealized_pnl_krw <= budget ? pos.qty : Math.floor(budget / pnlPerShare);
    // 주당 수익이 남은 예산보다 큰 종목은 건너뛰고, 주당 수익이 작은 다음 종목을 본다
    if (shares <= 0) continue;
    const realizedKrw = shares * pnlPerShare;
    profitRecs.push({
      pos,
      kind: "PROFIT",
      shares,
      realizedKrw,
      label: sellLabel(pos, shares),
      taxSaved: Math.round(realizedKrw * taxRate),
    });
    budget -= realizedKrw;
  }

  // 수익 실현이 하나도 없으면 손실만 파는 추천은 의미가 없다
  if (profitRecs.length === 0) return [];
  const lossRecs: TaxRecommendation[] = lossQueue.flatMap((loss, i) => {
    const shares = lossSharesUsed[i]!;
    if (shares <= 0) return [];
    return [
      {
        pos: loss,
        kind: "LOSS" as const,
        shares,
        realizedKrw: (loss.unrealized_pnl_krw / loss.qty) * shares,
        label: sellLabel(loss, shares),
        taxSaved: 0,
      },
    ];
  });
  return [...profitRecs, ...lossRecs];
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

  // 손실 매도 없이 공제 잔여만으로 무세 실현 — 손실 종목을 계속 들고 가려는 경우의 기본 추천
  const recommendations = useMemo(
    () =>
      hasAnyQtyInput
        ? []
        : buildTaxRecommendations(profitPositions, [], remainingDeduction, taxRate),
    [hasAnyQtyInput, profitPositions, remainingDeduction, taxRate],
  );
  // 손실 종목을 함께 팔아 통산하는 추천 — 실제로 손실 매도가 들어간 경우만(아니면 위와 같은 목록이라 빈 배열)
  const lossHarvestRecommendations = useMemo(() => {
    if (hasAnyQtyInput) return [];
    const recs = buildTaxRecommendations(
      profitPositions,
      lossPositions,
      remainingDeduction,
      taxRate,
    );
    return recs.some((r) => r.kind === "LOSS") ? recs : [];
  }, [hasAnyQtyInput, profitPositions, lossPositions, remainingDeduction, taxRate]);

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
    lossHarvestRecommendations,
    handleQtyChange,
  };
}
