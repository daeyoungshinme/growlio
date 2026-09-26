"""목표 달성 가능성 미리보기(필요 연수익률 + 가정 수익률별 필요 적립액) 계산 — `/invest/goal-feasibility`(growlio
목표 설정 마법사)와 `/external/goal-feasibility`(nestlio 재무목표 상세)가 공유한다. 두 엔드포인트는 현재 자산(pv)과
기간(n_months)을 구하는 방법만 다르고(growlio는 총자산 스냅샷·목표 연말까지, nestlio는 자기 목표의 현재 금액·
목표일까지), 그 뒤의 역산은 같다."""

from app.schemas.invest import DepositGuideItem, GoalFeasibilityPreview
from app.services.goal_return_solver import (
    DEPOSIT_GUIDE_PRESET_RETURNS_PCT,
    solve_required_annual_return_pct,
    solve_required_monthly_deposit,
)


def build_feasibility_preview(
    pv: float,
    goal_amount: float,
    n_months: int,
    monthly_deposit_amount: float,
    expired_note: str = "목표 시점이 이미 지났습니다 — 목표 시점을 다시 설정해주세요",
) -> GoalFeasibilityPreview:
    if n_months <= 0:
        return GoalFeasibilityPreview(required_return_pct=None, pv=pv, n_months=n_months, note=expired_note)
    if pv >= goal_amount:
        return GoalFeasibilityPreview(
            required_return_pct=None, pv=pv, n_months=n_months, note="이미 목표 금액을 달성했습니다"
        )

    required_return_pct = solve_required_annual_return_pct(pv, monthly_deposit_amount, n_months, goal_amount)
    note = None if required_return_pct is not None else "현재 조건(적립액·기간)으로는 달성이 매우 어려운 목표입니다"
    deposit_guide = []
    for preset_pct in DEPOSIT_GUIDE_PRESET_RETURNS_PCT:
        monthly = solve_required_monthly_deposit(pv, preset_pct, n_months, goal_amount)
        deposit_guide.append(
            DepositGuideItem(
                annual_return_pct=preset_pct,
                required_monthly_deposit=monthly,
                required_annual_deposit=monthly * 12,
            )
        )
    return GoalFeasibilityPreview(
        required_return_pct=required_return_pct,
        pv=pv,
        n_months=n_months,
        note=note,
        deposit_guide=deposit_guide,
    )
