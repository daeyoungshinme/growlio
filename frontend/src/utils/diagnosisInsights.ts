import type { DiagnosisContext } from "../api/rebalancing";
import type { MarketRiskLevel } from "../api/marketSignals";
import { fmtKrw } from "./format";

const FEE_NOTE_THRESHOLD_KRW = 10_000;
/** 손실실현(절세) 노트를 다른 tax_notes 항목과 구분하기 위한 마커 — diagnosis_service.py의 문구와 동기화 유지 */
const TAX_LOSS_REALIZED_MARKER = "절세 효과가 있습니다";

export type DiagnosisNoteIcon = "market" | "risk" | "tax";

export interface DiagnosisNote {
  icon: DiagnosisNoteIcon;
  text: string;
  /** 손실실현으로 절세 기회가 생긴 경우 — 세금 탭 딥링크 CTA를 함께 노출할지 여부 */
  isTaxLossOpportunity?: boolean;
}

/** DiagnosisContext를 화면에 표시할 조건부 인사이트 문구 리스트로 변환한다.
 * 세금 관련 문구는 백엔드(diagnosis_service.py의 _build_tax_preview)가 계산한 tax_notes를
 * 그대로 사용한다 — 실현손익 부호(이익/손실)에 따라 다른 문구가 필요해 프론트에서 재계산하지 않는다. */
export function buildDiagnosisNotes(ctx: DiagnosisContext): DiagnosisNote[] {
  const notes: DiagnosisNote[] = [];

  if (ctx.market_note) {
    notes.push({ icon: "market", text: ctx.market_note });
  }
  if (ctx.risk_note) {
    notes.push({ icon: "risk", text: ctx.risk_note });
  }

  for (const text of ctx.tax_notes) {
    notes.push({
      icon: "tax",
      text,
      isTaxLossOpportunity: text.includes(TAX_LOSS_REALIZED_MARKER),
    });
  }

  if (ctx.estimated_fee_krw > FEE_NOTE_THRESHOLD_KRW) {
    notes.push({
      icon: "tax",
      text: `이번 리밸런싱 매도 시 예상 매매 수수료 약 ${fmtKrw(ctx.estimated_fee_krw)} (참고용 추정치)`,
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
