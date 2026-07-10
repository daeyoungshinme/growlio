import type { DiagnosisContext } from "../api/rebalancing";
import type { MarketRiskLevel } from "../api/marketSignals";
import { fmtKrw } from "./format";

const TAX_IMPACT_NOTE_THRESHOLD_KRW = 10_000;

export type DiagnosisNoteIcon = "market" | "risk" | "tax";

export interface DiagnosisNote {
  icon: DiagnosisNoteIcon;
  text: string;
}

/** DiagnosisContext를 화면에 표시할 조건부 인사이트 문구 리스트로 변환한다. */
export function buildDiagnosisNotes(ctx: DiagnosisContext): DiagnosisNote[] {
  const notes: DiagnosisNote[] = [];

  if (ctx.market_note) {
    notes.push({ icon: "market", text: ctx.market_note });
  }
  if (ctx.risk_note) {
    notes.push({ icon: "risk", text: ctx.risk_note });
  }

  const taxImpact = ctx.estimated_overseas_tax_krw + ctx.estimated_fee_krw;
  if (taxImpact > TAX_IMPACT_NOTE_THRESHOLD_KRW) {
    notes.push({
      icon: "tax",
      text: `이번 리밸런싱 매도 시 예상 세금·수수료 영향 약 ${fmtKrw(taxImpact)} (참고용 추정치)`,
    });
  }

  return notes;
}

/** 대시보드 등에서 "이탈 종목 발견 + 시장상황"을 결합한 한 줄 설명을 만든다. */
export function buildCombinedStatusNote(
  needsCount: number,
  marketLevel: MarketRiskLevel | null | undefined,
): string | null {
  if (needsCount === 0 || !marketLevel || marketLevel === "GREEN") {
    return null;
  }
  return marketLevel === "RED"
    ? "시장 위험 신호가 높은 국면에서 이탈 종목이 발견되었습니다 — 신중하게 검토하세요."
    : "시장 변동성이 확대되는 국면에서 이탈 종목이 발견되었습니다 — 분할 실행을 고려해보세요.";
}
