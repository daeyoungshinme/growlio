"""설정 Pydantic 스키마 유효성 검사 단위 테스트."""
import pytest
from pydantic import ValidationError


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


class TestAutoDcaUpdate:
    def test_invalid_day_zero(self):
        from app.api.v1.settings import AutoDcaUpdate
        with pytest.raises(ValidationError):
            AutoDcaUpdate(enabled=True, day=0)

    def test_invalid_day_29(self):
        from app.api.v1.settings import AutoDcaUpdate
        with pytest.raises(ValidationError):
            AutoDcaUpdate(enabled=True, day=29)

    def test_valid_day(self):
        from app.api.v1.settings import AutoDcaUpdate
        obj = AutoDcaUpdate(enabled=True, day=15)
        assert obj.day == 15

    def test_invalid_amount_zero(self):
        from app.api.v1.settings import AutoDcaUpdate
        with pytest.raises(ValidationError):
            AutoDcaUpdate(enabled=True, amount=0)

    def test_invalid_amount_over_billion(self):
        from app.api.v1.settings import AutoDcaUpdate
        with pytest.raises(ValidationError):
            AutoDcaUpdate(enabled=True, amount=1_000_000_001)

    def test_valid_amount(self):
        from app.api.v1.settings import AutoDcaUpdate
        obj = AutoDcaUpdate(enabled=True, amount=500_000)
        assert obj.amount == 500_000
