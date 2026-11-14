import type { AssetAccount } from "@/api/assets";
import type { RebalancingAnalysis, RebalancingItem } from "@/api/rebalancing";
import { isOrderExecutableAccount } from "@/utils/accounts";
import {
  buyItemForAccount,
  canBuyInAccount,
  getActionableItems,
  orderKey,
} from "@/components/rebalancing/rebalancingTradeMath";

/**
 * 실행 모달을 열 때의 기본값 — 종목별 매수 계좌(보유 수량이 가장 많은 주문 가능 계좌, ISA·연금에서 살 수 없으면
 * 살 수 있는 첫 계좌)와 처음부터 선택해 둘 주문 키. 순수 함수.
 */
export function computeInitialBuyAndSelected(
  analysis: RebalancingAnalysis,
  tradableAccounts: AssetAccount[],
): { buyAccounts: Record<string, string[]>; selected: Set<string> } {
  const actionableItems = getActionableItems(analysis);
  const defaultAccId = tradableAccounts[0]?.id ?? "";

  function getPrimaryAccountId(ticker: string): string {
    const infos = (analysis.ticker_account_map[ticker] ?? []).filter((a) =>
      isOrderExecutableAccount(a.asset_type),
    );
    if (infos.length === 0) return defaultAccId;
    return infos.reduce((best, a) => (a.quantity > best.quantity ? a : best)).account_id;
  }

  const taxTypeOf = (accountId: string) =>
    tradableAccounts.find((a) => a.id === accountId)?.tax_type;

  // 기본 매수 계좌가 ISA·연금인데 그 종목을 살 수 없으면(해외 상장, 국내 대체 없음) 살 수 있는 첫 계좌로 바꾼다
  function getBuyAccountId(item: RebalancingItem): string {
    const primary = getPrimaryAccountId(item.ticker);
    if (canBuyInAccount(item, analysis.items, taxTypeOf(primary))) return primary;
    return (
      tradableAccounts.find((a) => canBuyInAccount(item, analysis.items, a.tax_type))?.id ?? primary
    );
  }

  const buyAccounts: Record<string, string[]> = {};
  const selected = new Set<string>();

  if (!defaultAccId) return { buyAccounts, selected };

  actionableItems.forEach((i) => {
    if ((i.shares_to_trade ?? 0) > 0) {
      buyAccounts[i.ticker] = [getBuyAccountId(i)];
    }
  });

  actionableItems.forEach((i) => {
    if ((i.shares_to_trade ?? 0) < 0) {
      (analysis.ticker_account_map[i.ticker] ?? [])
        .filter((a) => isOrderExecutableAccount(a.asset_type))
        .forEach((a) => selected.add(orderKey("sell", i.ticker, a.account_id)));
    } else if ((i.shares_to_trade ?? 0) > 0) {
      const accId = buyAccounts[i.ticker]?.[0];
      if (!accId) return;
      // ISA·연금 계좌면 실제로 사는 종목(국내 대체)의 키로 선택해 둔다 — getBuyRows와 같은 판단
      const buyItem = buyItemForAccount(i, analysis.items, taxTypeOf(accId));
      selected.add(orderKey("buy", buyItem.ticker, accId));
    }
  });

  return { buyAccounts, selected };
}
