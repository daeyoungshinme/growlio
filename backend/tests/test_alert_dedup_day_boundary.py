"""알림 "오늘 이미 보냈나" 판정의 하루 경계가 KST 자정인지 (plans/61 A2).

UTC 자정(=KST 09:00)을 쓰면 08:30 KST 다이제스트 이력이 같은 날로 잡히지 않아 재실행 시 중복 발송된다.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.utils.kst import KST

_TODAY = date(2026, 10, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module_path", "func_name"),
    [
        ("app.services.alerts.market_signal_alert_service", "_already_sent_digest_today"),
        ("app.services.alerts.recommendation_drift_alert_service", "_already_sent_this_week"),
        ("app.services.alerts.tax_reminder_service", "_already_sent_reminder_today"),
    ],
)
async def test_day_start_is_kst_midnight(module_path: str, func_name: str):
    import importlib

    module = importlib.import_module(module_path)
    result = MagicMock()
    result.scalar.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    with patch(f"{module_path}.today_kst", return_value=_TODAY):
        await getattr(module, func_name)(db, uuid.uuid4())

    stmt = db.execute.call_args[0][0]
    bound = [v for v in stmt.compile().params.values() if isinstance(v, datetime)]
    assert bound == [datetime(2026, 10, 1, tzinfo=KST)]
