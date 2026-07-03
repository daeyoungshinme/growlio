"""배당 현금흐름 최적화 — 월별 균등화 제안."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 월별 균등화 제안
# ---------------------------------------------------------------------------


def calc_monthly_optimization(
    ticker_summaries: list[dict],
) -> list[dict]:
    """배당이 약한 달에 수령 가능한 종목 추천.

    Returns:
        월별로 추가 매수하면 배당이 생기는 종목 추천 목록.
        weak_months: 배당 수령이 없거나 적은 달.
        suggestions: [{month, ticker, name, estimated_monthly_krw}]
    """
    # 현재 월별 예상 배당 합계 계산
    monthly_totals: dict[int, float] = {m: 0.0 for m in range(1, 13)}
    for item in ticker_summaries:
        months: list[int] = item.get("dividend_months") or []
        estimated_annual = float(item.get("estimated_annual_krw") or 0)
        if not months or estimated_annual <= 0:
            continue
        per_payment = estimated_annual / len(months)
        for month in months:
            if 1 <= month <= 12:
                monthly_totals[month] += per_payment

    avg_monthly = sum(monthly_totals.values()) / 12 if any(monthly_totals.values()) else 0
    threshold = avg_monthly * 0.5

    weak_months = [m for m, total in monthly_totals.items() if total < threshold]
    if not weak_months:
        return []

    suggestions: list[dict] = []
    for item in ticker_summaries:
        item_months: list[int] = item.get("dividend_months") or []
        estimated_annual = float(item.get("estimated_annual_krw") or 0)
        if not item_months or estimated_annual <= 0:
            continue

        for weak_month in weak_months:
            if weak_month in item_months:
                per_payment = estimated_annual / len(item_months)
                suggestions.append(
                    {
                        "month": weak_month,
                        "ticker": item.get("ticker", ""),
                        "name": item.get("name") or item.get("ticker", ""),
                        "market": item.get("market", ""),
                        "estimated_monthly_krw": round(per_payment, 0),
                        "current_monthly_total_krw": round(monthly_totals[weak_month], 0),
                    }
                )

    # 약한 달, 추정금액 기준 정렬
    suggestions.sort(key=lambda x: (x["month"], -x["estimated_monthly_krw"]))

    # 동일 달 내 상위 3개만
    filtered: list[dict] = []
    month_counts: dict[int, int] = {}
    for s in suggestions:
        cnt = month_counts.get(s["month"], 0)
        if cnt < 3:
            filtered.append(s)
            month_counts[s["month"]] = cnt + 1

    return filtered
