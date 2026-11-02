import type { TxType } from "@/constants/transaction";

function signedAmount(amount: number, txType: string): number {
  return txType === "WITHDRAWAL" ? -amount : amount;
}

/**
 * 거래 수정 후 예수금에 반영을 제안할 금액 — 수정 전후 차액만이다.
 * 전액을 제안하면 메모만 고쳐도 이미 반영한 금액이 이중으로 더해진다.
 * 차액이 없으면 amount 0(호출부의 제안 함수가 0은 무시한다).
 */
export function depositDeltaAfterEdit(
  previous: { amount: number; transaction_type: string } | null,
  amount: number,
  txType: string,
): { amount: number; txType: TxType } {
  const before = previous ? signedAmount(previous.amount, previous.transaction_type) : 0;
  const diff = signedAmount(amount, txType) - before;
  return { amount: Math.abs(diff), txType: diff < 0 ? "WITHDRAWAL" : "DEPOSIT" };
}
