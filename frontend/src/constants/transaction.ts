export const TX_TYPES = ["DEPOSIT", "WITHDRAWAL", "DIVIDEND"] as const;
export type TxType = (typeof TX_TYPES)[number];

export const CURRENCY_TYPES = ["KRW", "USD"] as const;
export type CurrencyType = (typeof CURRENCY_TYPES)[number];

export const TX_LABELS: Record<string, string> = {
  DEPOSIT: "입금",
  WITHDRAWAL: "출금",
  DIVIDEND: "배당",
};

export const TX_COLORS: Record<string, string> = {
  DEPOSIT: "text-blue-600",
  WITHDRAWAL: "text-red-500",
  DIVIDEND: "text-green-600",
};
