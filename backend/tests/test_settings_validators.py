"""설정 Pydantic 스키마 유효성 검사 단위 테스트."""

import pytest
from pydantic import ValidationError


class TestValidatePortfolioWeightsOptional:
    def test_none_input_returns_none(self):
        from app.schemas._validators import validate_portfolio_weights_optional

        result = validate_portfolio_weights_optional(None)
        assert result is None

    def test_valid_items_delegates_to_validate_weights(self):
        from types import SimpleNamespace

        from app.schemas._validators import validate_portfolio_weights_optional

        items = [SimpleNamespace(ticker="T", weight=60.0), SimpleNamespace(ticker="T", weight=40.0)]
        result = validate_portfolio_weights_optional(items)
        assert result is items

    def test_invalid_items_raises(self):
        from types import SimpleNamespace

        import pytest

        from app.schemas._validators import validate_portfolio_weights_optional

        items = [SimpleNamespace(ticker="T", weight=50.0)]  # sum != 100
        with pytest.raises(ValueError, match="비중 합계가"):
            validate_portfolio_weights_optional(items)


class TestGoalUpdate:
    def test_negative_goal_amount_raises(self):
        from app.api.v1.settings import GoalUpdate

        with pytest.raises(ValidationError):
            GoalUpdate(goal_amount=-1)

    def test_valid_goal_amount(self):
        from app.api.v1.settings import GoalUpdate

        obj = GoalUpdate(goal_amount=100_000_000)
        assert obj.goal_amount == 100_000_000

    def test_invalid_return_pct_over_100(self):
        from app.api.v1.settings import GoalUpdate

        with pytest.raises(ValidationError):
            GoalUpdate(goal_annual_return_pct=101.0)

    def test_invalid_return_pct_negative(self):
        from app.api.v1.settings import GoalUpdate

        with pytest.raises(ValidationError):
            GoalUpdate(goal_annual_return_pct=-1.0)

    def test_valid_return_pct(self):
        from app.api.v1.settings import GoalUpdate

        obj = GoalUpdate(goal_annual_return_pct=7.5)
        assert obj.goal_annual_return_pct == 7.5

    def test_invalid_retirement_year_in_past(self):
        from app.api.v1.settings import GoalUpdate

        with pytest.raises(ValidationError):
            GoalUpdate(retirement_target_year=2000)

    def test_valid_retirement_year(self):
        from app.api.v1.settings import GoalUpdate

        obj = GoalUpdate(retirement_target_year=2040)
        assert obj.retirement_target_year == 2040

    def test_rejects_retirement_year_too_far(self):
        # 10000을 저장하면 목표 추천의 date(target_year, 12, 31)이 매번 500을 냈다(계획 57 C4)
        from app.api.v1.settings import GoalUpdate

        with pytest.raises(ValidationError):
            GoalUpdate(retirement_target_year=10000)

    def test_rejects_goal_amount_above_cap(self):
        from app.api.v1.settings import GoalUpdate

        with pytest.raises(ValidationError):
            GoalUpdate(goal_amount=1e17)


class TestSchemaBounds61:
    """DB 컬럼 한도를 넘는 입력은 500이 아니라 422 (plans/61 D)."""

    def test_sync_profile_display_name_max_length(self):
        import pytest
        from pydantic import ValidationError

        from app.schemas.auth import SyncProfileRequest

        assert SyncProfileRequest(display_name="가" * 100).display_name
        with pytest.raises(ValidationError):
            SyncProfileRequest(display_name="가" * 101)

    def test_isa_pnl_override_bounds(self):
        import pytest
        from pydantic import ValidationError

        from app.schemas.asset import IsaPnlOverrideUpdate

        assert IsaPnlOverrideUpdate(cumulative_pnl_krw=-1_500_000).cumulative_pnl_krw == -1_500_000
        assert IsaPnlOverrideUpdate(cumulative_pnl_krw=None).cumulative_pnl_krw is None
        for bad in (float("nan"), float("inf"), 1e17, -1e17):
            with pytest.raises(ValidationError):
                IsaPnlOverrideUpdate(cumulative_pnl_krw=bad)
