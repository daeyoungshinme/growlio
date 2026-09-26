"""정기 적립식 자동매수 예수금 부족 사전 알림 Job(jobs/dca_cash_shortfall) — 계획 37 E5."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.jobs import dca_cash_shortfall as job


def _alert(day=25):
    return SimpleNamespace(
        id=uuid.uuid4(),
        schedule_type="MONTHLY",
        schedule_day_of_month=day,
        schedule_day_of_week=None,
        trigger_condition="SCHEDULE_ONLY",
        mode="AUTO",
        strategy="BUY_ONLY",
        last_triggered_at=None,
    )


def _portfolio(markets=("KOSPI",)):
    return SimpleNamespace(name="성장 적립", items=[SimpleNamespace(market=m) for m in markets])


def _account(deposit_krw=300_000.0, deposit_usd=None):
    return SimpleNamespace(
        name="키움 연금", deposit_krw=deposit_krw, deposit_usd=deposit_usd, last_synced_at=None, is_active=True
    )


def _user():
    return SimpleNamespace(id=uuid.uuid4(), email="u@test.com")


def _settings(monthly=1_000_000.0):
    return SimpleNamespace(monthly_deposit_amount=monthly, notification_email=None, fcm_token="tok")


def _db(rows):
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = rows
    db.execute = AsyncMock(return_value=result)
    return db


async def _run(rows, today, *, durable=None, usd_krw=1400.0):
    dispatch = AsyncMock(return_value=True)
    with (
        patch.object(job, "today_kst", return_value=today),
        patch.object(job, "get_durable", new=AsyncMock(return_value=durable)),
        patch.object(job, "set_durable", new=AsyncMock()),
        patch.object(job, "dispatch_dual_channel_alert", new=dispatch),
        patch.object(job, "fetch_usd_krw", new=AsyncMock(return_value=usd_krw)),
    ):
        await job._run_dca_cash_shortfall_check(_db(rows), MagicMock())
    return dispatch


@pytest.mark.asyncio
async def test_notifies_when_cash_below_monthly_amount_within_window():
    rows = [(_alert(25), _portfolio(), _account(300_000), _user(), _settings(1_000_000))]
    dispatch = await _run(rows, date(2026, 11, 23))  # 25일(수)까지 2일

    dispatch.assert_awaited_once()
    kwargs = dispatch.await_args.kwargs
    assert kwargs["alert_type"] == "DCA_CASH_SHORTFALL"
    assert kwargs["push_type"] == "DCA_CASH_SHORTFALL"
    assert "11월 25일(수)" in kwargs["push_body"]
    assert "700,000원 부족" in kwargs["push_body"]


@pytest.mark.parametrize("today", [date(2026, 11, 20), date(2026, 11, 25)])
@pytest.mark.asyncio
async def test_no_notice_outside_window(today):
    """실행일 4일 이상 전이거나 당일(다음 실행일은 다음 달)이면 알리지 않는다."""
    rows = [(_alert(25), _portfolio(), _account(0), _user(), _settings())]
    dispatch = await _run(rows, today)
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_notice_when_cash_is_enough():
    rows = [(_alert(25), _portfolio(), _account(1_200_000), _user(), _settings(1_000_000))]
    dispatch = await _run(rows, date(2026, 11, 24))
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_dedup_skips_already_notified_run_date():
    rows = [(_alert(25), _portfolio(), _account(0), _user(), _settings())]
    dispatch = await _run(rows, date(2026, 11, 24), durable="1")
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_weekend_run_date_uses_rolled_monday():
    """2026-10-25(일) 지정 → 실제 실행 10/26(월) 기준으로 1~3일 전(10/23 금)에 알린다."""
    rows = [(_alert(25), _portfolio(), _account(0), _user(), _settings())]
    dispatch = await _run(rows, date(2026, 10, 23))
    dispatch.assert_awaited_once()
    assert "10월 26일(월)" in dispatch.await_args.kwargs["push_body"]


@pytest.mark.parametrize(
    ("cash", "expected", "short"),
    [(5_000, None, True), (50_000, None, False), (999_999, 1_000_000, True), (1_000_000, 1_000_000, False)],
)
def test_is_cash_short(cash, expected, short):
    """월 적립액 미설정이면 1만원 미만(사실상 빈 계좌)일 때만 부족으로 본다."""
    assert job.is_cash_short(cash, expected) is short


def test_usd_counted_only_when_portfolio_has_overseas_items():
    account = _account(deposit_krw=100_000, deposit_usd=100)
    assert job.account_cash_krw(account, _portfolio(("KOSPI",)), 1400.0) == 100_000
    assert job.account_cash_krw(account, _portfolio(("KOSPI", "NASDAQ")), 1400.0) == 240_000


def test_is_dca_auto_buy_matches_frontend_preset():
    assert job.is_dca_auto_buy(_alert())
    notify = _alert()
    notify.mode = "NOTIFY"
    assert not job.is_dca_auto_buy(notify)


def test_email_template_shows_shortfall_and_run_date():
    from app.services.email_templates import dca_cash_shortfall_template

    subject, html = dca_cash_shortfall_template(
        "성장 적립", "키움 연금", "11월 25일(수)", 300_000, 1_000_000, "11/23 18:00"
    )
    assert "11월 25일(수)" in subject
    assert "700,000 원" in html
    assert "11/23 18:00 동기화 기준" in html
