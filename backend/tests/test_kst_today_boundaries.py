"""사용자 기준 "오늘"이 KST로 계산되는지 — UTC로는 전날인 KST 새벽(00:00~09:00) 경계 케이스.

운영 서버는 UTC라 `datetime.now(UTC)`를 쓰면 이 시간대에 날짜·연도가 하루(해) 밀린다.
`app.utils.kst.datetime`만 고정해 `today_kst()`/`now_kst()`를 경유하는 모든 지점을 함께 검증한다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.enums import AgeGroup
from app.services import tax_service
from app.services.goal_age_recommendation_service import age_group_from_birth_year
from app.services.rebalancing import plan_notifications
from app.services.rebalancing.plan_generation import MarketSignalGateBlocked, TaxGateBlocked

# 2026-12-31 20:00 UTC == 2027-01-01 05:00 KST
_INSTANT = datetime(2026, 12, 31, 20, 0, tzinfo=UTC)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return _INSTANT.astimezone(tz) if tz else _INSTANT.replace(tzinfo=None)


@pytest.fixture
def kst_new_year_dawn():
    with patch("app.utils.kst.datetime", _FrozenDatetime):
        yield


def test_age_group_uses_kst_year(kst_new_year_dawn):
    # KST 2027년 기준 30세 → THIRTIES (UTC 2026년이면 29세 → TWENTIES)
    assert age_group_from_birth_year(1997) == AgeGroup.THIRTIES


def test_overseas_transfer_tax_default_year_is_kst(kst_new_year_dawn):
    with patch.object(tax_service, "_get_rates", wraps=tax_service._get_rates) as mock_rates:
        tax_service.estimate_overseas_transfer_tax(1_000_000.0)
    mock_rates.assert_called_once_with(2027)


def _alert_and_portfolio():
    return SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4(), name="P")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("notify", "blocked"),
    [
        (
            plan_notifications.notify_tax_gate_blocked,
            TaxGateBlocked(estimated_tax_krw=200_000.0, max_tax_impact_krw=100_000.0),
        ),
        (
            plan_notifications.notify_market_signal_gate_blocked,
            MagicMock(spec=MarketSignalGateBlocked),
        ),
    ],
)
async def test_gate_alert_dedup_key_uses_kst_date(kst_new_year_dawn, notify, blocked):
    alert, portfolio = _alert_and_portfolio()
    get_durable = AsyncMock(return_value="1")  # 이미 발송됨 → 키만 확인하고 조기 반환
    with patch("app.utils.durable_state.get_durable", new=get_durable):
        await notify(alert, portfolio, blocked, "u@test.com", None, AsyncMock())

    dedup_key = get_durable.await_args.args[1]
    assert "2027-01-01" in dedup_key
