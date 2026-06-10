import type { PortfolioPosition, AggregatedPosition } from "@/types";

export interface AggregatedPositionWithSubs extends AggregatedPosition {
  sub_positions: PortfolioPosition[];
}

export function groupPositionsByTicker(positions: PortfolioPosition[]): AggregatedPositionWithSubs[] {
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
    agg.pnl_pct = agg.total_invested_krw > 0
      ? (agg.total_pnl / agg.total_invested_krw) * 100
      : 0;
  }
  return Array.from(map.values());
}
