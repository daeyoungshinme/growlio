"""app/utils/kst.py — 서버 TZ(UTC)와 무관하게 KST 기준 날짜를 돌려주는지."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

from app.services.email_templates.rebalancing import _to_kst
from app.utils.kst import KST, today_kst


class _FakeDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        # UTC 2026-09-30 23:30 = KST 2026-10-01 08:30
        base = datetime(2026, 9, 30, 23, 30, tzinfo=UTC)
        return base.astimezone(tz) if tz else base.replace(tzinfo=None)


def test_today_kst_rolls_over_before_utc_midnight():
    with patch("app.utils.kst.datetime", _FakeDatetime):
        assert today_kst() == date(2026, 10, 1)


def test_to_kst_converts_aware_and_treats_naive_as_utc():
    aware = datetime(2026, 9, 30, 23, 30, tzinfo=UTC)
    assert _to_kst(aware).strftime("%Y-%m-%d %H:%M") == "2026-10-01 08:30"
    assert _to_kst(aware.replace(tzinfo=None)) == _to_kst(aware)
    assert _to_kst(aware).tzinfo == KST
