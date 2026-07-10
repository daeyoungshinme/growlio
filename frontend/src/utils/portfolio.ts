import type { PortfolioPosition, AggregatedPosition } from "@/types";
import type { RebalancingAlert } from "@/api/alerts";
import type { Portfolio } from "@/api/portfolios";
import type { AssetAccount } from "@/api/assets";

export interface AggregatedPositionWithSubs extends AggregatedPosition {
  sub_positions: PortfolioPosition[];
}

export function groupPositionsByTicker(
  positions: PortfolioPosition[],
): AggregatedPositionWithSubs[] {
  const map = new Map<string, AggregatedPositionWithSubs>();
  for (const p of positions) {
    const key = `${p.ticker}-${p.market}`;
    const existing = map.get(key);
    if (!existing) {
      map.set(key, {
        ticker: p.ticker,
        name: p.name,
        market: p.market,
        currency: p.currency,
        total_qty: p.qty,
        weighted_avg_price: p.avg_price,
        current_price: p.current_price,
        total_value_krw: p.value_krw,
        total_invested_krw: p.invested_krw,
        total_pnl: p.pnl,
        pnl_pct: 0,
        weight_in_stock: p.weight_in_stock,
        sub_positions: [p],
      });
    } else {
      existing.total_qty += p.qty;
      existing.total_value_krw += p.value_krw;
      existing.total_invested_krw += p.invested_krw;
      existing.total_pnl += p.pnl;
      existing.weight_in_stock += p.weight_in_stock;
      existing.sub_positions.push(p);
    }
  }
  for (const agg of map.values()) {
    agg.pnl_pct = agg.total_invested_krw > 0 ? (agg.total_pnl / agg.total_invested_krw) * 100 : 0;
  }
  return Array.from(map.values());
}

/**
 * PER_ACCOUNT 스코프 포트폴리오는 계좌마다 독립된 알림 행을 가질 수 있다.
 * portfolio_id 기준으로 병합하되, 그중 하나라도 AUTO면 병합 결과의 mode를 AUTO로 표시한다.
 */
/**
 * target_portfolio_id는 계좌 1개당 1개만 가리키는 라벨이라, 계좌가 여러 포트폴리오의
 * account_ids(실제 분석 대상)에 동시에 속해도 "목표" 배지는 그중 하나에만 표시될 수 있다.
 */
export function getPortfolioTargetState(
  portfolio: Portfolio,
  stockAccounts: AssetAccount[],
): "full" | "partial" | "none" {
  const linkedIds = portfolio.account_ids?.length
    ? portfolio.account_ids
    : stockAccounts.map((a) => a.id);
  const relevant = stockAccounts.filter((a) => linkedIds.includes(a.id));
  if (relevant.length === 0) return "none";
  const assigned = relevant.filter((a) => a.target_portfolio_id === portfolio.id).length;
  if (assigned === 0) return "none";
  return assigned === relevant.length ? "full" : "partial";
}

export function mergeAlertsByPortfolio(
  alerts: RebalancingAlert[],
): Record<string, RebalancingAlert> {
  const map = new Map<string, RebalancingAlert[]>();
  for (const a of alerts) {
    const list = map.get(a.portfolio_id) ?? [];
    list.push(a);
    map.set(a.portfolio_id, list);
  }
  return Object.fromEntries(
    Array.from(map.entries()).map(([portfolioId, rows]) => [
      portfolioId,
      { ...rows[0], mode: rows.some((r) => r.mode === "AUTO") ? ("AUTO" as const) : rows[0].mode },
    ]),
  );
}
