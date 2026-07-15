import type { PortfolioPosition, AggregatedPosition } from "@/types";
import type { RebalancingAlert } from "@/api/alerts";
import type { Portfolio } from "@/api/portfolios";
import type { AccountTaxType, AssetAccount, InvestmentHorizon } from "@/api/assets";

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
 * account_ids(실제 분석 대상)에 동시에 속해도 "기준" 배지는 그중 하나에만 표시될 수 있다.
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

/**
 * 포트폴리오에 명시적으로 지정된 investment_horizon 태그가 있으면 그 값을 우선 사용한다.
 * 없으면(과거 생성된 포트폴리오 등) "기준 포트폴리오"로 지정된 계좌들이 전부 동일한 태그를
 * 가질 때만 역으로 추론한다 — 기간별 추천(RecommendationCard) 적용 시 어느 포트폴리오가 어느
 * 기간(단기/중기/장기) 담당인지 판별하는 데 쓰인다. 명시값도 추론값도 없으면 null.
 */
export function getPortfolioHorizon(
  portfolio: Portfolio,
  stockAccounts: AssetAccount[],
): InvestmentHorizon | null {
  if (portfolio.investment_horizon) return portfolio.investment_horizon;
  const assigned = stockAccounts.filter((a) => a.target_portfolio_id === portfolio.id);
  if (assigned.length === 0) return null;
  const horizon = assigned[0].investment_horizon;
  if (!horizon) return null;
  return assigned.every((a) => a.investment_horizon === horizon) ? horizon : null;
}

/**
 * 포트폴리오에 명시적으로 지정된 investment_horizon **및** tax_type 태그가 모두 있으면 그 조합을
 * 우선 사용한다. 없으면 "기준 포트폴리오"로 지정된 계좌들이 전부 동일한 두 태그를 가질 때만
 * 역으로 추론한다 — 계좌 세제유형까지 반영된 기간별 추천(RecommendationCard)을 적용할 때 어느
 * 포트폴리오가 어느 (기간, 세제유형) 카드를 담당하는지 판별하는 데 쓰인다. 명시값도 추론값도
 * 없으면 null.
 */
export function getPortfolioHorizonTaxType(
  portfolio: Portfolio,
  stockAccounts: AssetAccount[],
): { horizon: InvestmentHorizon; taxType: AccountTaxType } | null {
  if (portfolio.investment_horizon && portfolio.tax_type) {
    return { horizon: portfolio.investment_horizon, taxType: portfolio.tax_type };
  }
  const assigned = stockAccounts.filter((a) => a.target_portfolio_id === portfolio.id);
  if (assigned.length === 0) return null;
  const horizon = assigned[0].investment_horizon;
  const taxType = assigned[0].tax_type;
  if (!horizon || !taxType) return null;
  const matches = assigned.every((a) => a.investment_horizon === horizon && a.tax_type === taxType);
  return matches ? { horizon, taxType } : null;
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
