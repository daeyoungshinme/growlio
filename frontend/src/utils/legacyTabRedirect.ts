/**
 * 탭 구조 개편(plans/50)으로 위치가 바뀐 옛 딥링크를 새 위치로 옮긴다.
 * 이메일·푸시·외부에 저장된 링크가 계속 살아 있어야 하므로 리다이렉트로 유지한다.
 *
 * - `/assets?portfolioTab=세금[&taxTab=..][&account=..]` → `/invest-plan?tab=절세[&taxTab=..][&taxAccount=..]`
 * - `/assets?tab=계좌관리&atab=입출금·배당` → `atab=내역&history=현금 흐름`
 * - `/assets?tab=계좌관리&atab=기간별 매수` → `atab=내역&history=매수 내역`
 */
export function legacyAssetsTaxRedirect(searchParams: URLSearchParams): string | null {
  if (searchParams.get("portfolioTab") !== "세금") return null;
  const next = new URLSearchParams({ tab: "절세" });
  const taxTab = searchParams.get("taxTab");
  if (taxTab) next.set("taxTab", taxTab);
  const account = searchParams.get("account");
  if (account) next.set("taxAccount", account);
  return `/invest-plan?${next.toString()}`;
}

const LEGACY_HISTORY_ATABS: Record<string, string> = {
  "입출금·배당": "현금 흐름",
  "기간별 매수": "매수 내역",
};

/** 옛 계좌관리 하위탭(atab)이면 새 "내역" 탭의 세그먼트 이름을, 아니면 null을 돌려준다. */
export function legacyHistorySegment(atab: string | null): string | null {
  return atab ? (LEGACY_HISTORY_ATABS[atab] ?? null) : null;
}
