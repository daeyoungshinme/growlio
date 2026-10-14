import { fmtKrw } from "@/utils/format";

export const TX_TYPES = ["DEPOSIT", "WITHDRAWAL", "DIVIDEND", "INTEREST"] as const;
export type TxType = (typeof TX_TYPES)[number];

export const CURRENCY_TYPES = ["KRW", "USD"] as const;
export type CurrencyType = (typeof CURRENCY_TYPES)[number];

export const TX_LABELS: Record<string, string> = {
  DEPOSIT: "입금",
  WITHDRAWAL: "출금",
  DIVIDEND: "배당",
  INTEREST: "이자",
};

/** 입출금·배당 기록 삭제 확인 문구 — 어떤 기록이 지워지는지 날짜·유형·금액으로 보여준다. */
export function txDeleteConfirmMessage(tx: {
  transaction_date: string;
  transaction_type: string;
  amount: number;
}): string {
  const label = TX_LABELS[tx.transaction_type] ?? tx.transaction_type;
  return `${tx.transaction_date} ${label} ${fmtKrw(tx.amount)} 기록을 삭제할까요? 삭제하면 되돌릴 수 없어요.`;
}

export const TX_COLORS: Record<string, string> = {
  DEPOSIT: "text-blue-600",
  WITHDRAWAL: "text-red-500",
  DIVIDEND: "text-green-600",
  INTEREST: "text-teal-600",
};
