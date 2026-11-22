import type { AssetAccount } from "@/api/assets";

/** 계좌관리 목록 정렬(plans/144 C3). "default"는 서버 순서(sort_order → 생성일)를 그대로 둔다. */
export const ACCOUNT_SORT_MODES = ["default", "amount", "name"] as const;
export type AccountSortMode = (typeof ACCOUNT_SORT_MODES)[number];

export const ACCOUNT_SORT_OPTIONS: { value: AccountSortMode; label: string }[] = [
  { value: "default", label: "기본" },
  { value: "amount", label: "금액순" },
  { value: "name", label: "이름순" },
];

export function parseAccountSortMode(raw: string | null): AccountSortMode {
  return (ACCOUNT_SORT_MODES as readonly string[]).includes(raw ?? "")
    ? (raw as AccountSortMode)
    : "default";
}

/** 원본을 바꾸지 않고 정렬한 새 배열. 금액이 같으면 서버 순서를 유지한다(안정 정렬). */
export function sortAccounts<T>(
  items: readonly T[],
  mode: AccountSortMode,
  amountOf: (item: T) => number,
  nameOf: (item: T) => string,
): T[] {
  if (mode === "default") return [...items];
  const indexed = items.map((item, i) => ({ item, i }));
  indexed.sort((a, b) => {
    const diff =
      mode === "amount"
        ? amountOf(b.item) - amountOf(a.item)
        : nameOf(a.item).localeCompare(nameOf(b.item), "ko");
    return diff !== 0 ? diff : a.i - b.i;
  });
  return indexed.map(({ item }) => item);
}

/** 은행·현금 계좌의 원화 잔액. 예수금 필드가 있으면 원화 + 달러 환산, 없으면 수기 금액.
 * 환율이 없으면 달러는 더하지 않고 `usdPending`으로 알린다 — 0원으로 더해 합계가 조용히 줄지 않게. */
export function bankBalanceKrw(
  account: Pick<AssetAccount, "deposit_krw" | "deposit_usd" | "manual_amount">,
  usdRate: number | null,
): { krw: number; usd: number; usdPending: boolean; hasDepositFields: boolean } {
  const hasDepositFields = account.deposit_krw != null || account.deposit_usd != null;
  const usd = account.deposit_usd ?? 0;
  if (!hasDepositFields) {
    return { krw: account.manual_amount ?? 0, usd: 0, usdPending: false, hasDepositFields };
  }
  return {
    krw: (account.deposit_krw ?? 0) + (usdRate ? usd * usdRate : 0),
    usd,
    usdPending: usd > 0 && !usdRate,
    hasDepositFields,
  };
}
